from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..models import (
    BarterContract,
    Collateral,
    CollateralStatus,
    ContractStatus,
    CreditTransaction,
    EventLog,
    Prediction,
    PredictionEvaluation,
    Provider,
    RenegotiationEvent,
    ReputationHistory,
    ResourceState,
    ShortageEvent,
    StochasticEvent,
)
from ..schemas import (
    ActionResponse,
    ContractOut,
    CreateContractRequest,
    CreditTransactionOut,
    EventOut,
    MatchSuggestion,
    PredictionOut,
    ProviderOut,
    RenegotiationEventOut,
    ReputationHistoryOut,
    ResourceStateOut,
    SettlementRequest,
    SimulationSpeedRequest,
    SimulationStepRequest,
    SimulationConfigureRequest,
    InjectEventRequest,
)
from ..config import get_settings
from ..services.analytics_service import analytics_summary, credit_timelines, provider_analytics
from ..services.contract_service import complete_contract, create_contract, fail_contract, transition_to_active
from ..services.event_service import record_event
from ..services.matching_service import find_matches
from ..services.renegotiation_service import reevaluate_and_renegotiate
from ..simulation.prediction_generator import generate_initial_predictions
from ..simulation.control_service import pause as pause_simulation
from ..simulation.control_service import reset as reset_simulation
from ..simulation.control_service import (
    configure as configure_simulation,
    generate_seed_and_restart,
    restart_same_seed,
    set_speed,
    start as start_simulation,
    step_forward,
)
from ..simulation.simulation_state import get_or_create_state, state_payload
from ..simulation.event_generator import inject_workload_event
from ..simulation.failure_generator import inject_failure
from ..simulation.engine import sample_resources
from ..simulation.mutation_lock import simulation_mutation
from ..simulation.run_service import list_run_summaries
from ..simulation.workload_profiles import personality

router = APIRouter(prefix="/api")


def current_matches(db: Session):
    state = get_or_create_state(db)
    cycle_id = db.scalar(
        select(Prediction.cycle_id).where(
            Prediction.run_id == state.current_run_id,
            Prediction.superseded.is_(False),
            Prediction.cycle_id.is_not(None),
        ).order_by(Prediction.simulation_generated_at.desc(), Prediction.id.desc())
    )
    return find_matches(db, cycle_id=cycle_id) if cycle_id else find_matches(db)


def prediction_payload(prediction: Prediction) -> dict:
    payload = PredictionOut.model_validate(prediction).model_dump()
    payload["provider_name"] = prediction.provider.name
    return payload


def contract_payload(contract: BarterContract) -> dict:
    return {
        "id": contract.id,
        "run_id": contract.run_id,
        "provider_id": contract.provider_id,
        "provider_name": contract.provider.name,
        "consumer_id": contract.consumer_id,
        "consumer_name": contract.consumer.name,
        "prediction_id": contract.prediction_id,
        "parent_contract_id": contract.parent_contract_id,
        "cpu_amount": contract.cpu_amount,
        "ram_amount": contract.ram_amount,
        "start_time": contract.start_time,
        "end_time": contract.end_time,
        "barter_cost": contract.barter_cost,
        "prediction_confidence": contract.prediction_confidence,
        "status": contract.status,
        "match_score": contract.match_score,
        "selection_reason": contract.selection_reason,
        "actual_cpu_spare": contract.actual_cpu_spare,
        "actual_ram_spare": contract.actual_ram_spare,
        "collateral": contract.collateral,
        "created_at": contract.created_at,
        "updated_at": contract.updated_at,
        "created_simulation_time": contract.created_simulation_time,
        "barter_type": contract.barter_type,
        "emergency_reason": contract.emergency_reason,
        "reaction_time_minutes": contract.reaction_time_minutes,
    }


def get_contract_or_404(db: Session, contract_id: int) -> BarterContract:
    contract = db.scalar(
        select(BarterContract)
        .where(BarterContract.id == contract_id)
        .options(
            selectinload(BarterContract.provider),
            selectinload(BarterContract.consumer),
            selectinload(BarterContract.collateral),
            selectinload(BarterContract.prediction),
        )
    )
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    return contract


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/providers", response_model=list[ProviderOut])
def list_providers(db: Session = Depends(get_db)):
    simulation = get_or_create_state(db)
    providers = db.scalars(select(Provider).order_by(Provider.id)).all()
    result = []
    for provider in providers:
        state = db.scalar(
            select(ResourceState)
            .where(ResourceState.run_id == simulation.current_run_id, ResourceState.provider_id == provider.id)
            .order_by(ResourceState.simulation_time.desc(), ResourceState.id.desc())
        )
        prediction_query = (
            select(Prediction)
            .where(
                Prediction.run_id == simulation.current_run_id,
                Prediction.provider_id == provider.id,
                Prediction.superseded.is_(False),
            )
            .order_by(Prediction.simulation_generated_at.desc(), Prediction.horizon_minutes.desc(), Prediction.id.desc())
        )
        prediction = db.scalar(prediction_query.where(Prediction.horizon_minutes == get_settings().planning_horizon_minutes))
        if prediction is None:
            prediction = db.scalar(prediction_query)
        commitments = db.scalars(
            select(BarterContract).where(
                BarterContract.provider_id == provider.id,
                BarterContract.run_id == simulation.current_run_id,
                BarterContract.status.in_([
                    ContractStatus.PROPOSED,
                    ContractStatus.SCHEDULED,
                    ContractStatus.AT_RISK,
                    ContractStatus.ACTIVE,
                ]),
            )
        ).all()
        locked_collateral = db.scalars(
            select(Collateral).where(
                Collateral.provider_id == provider.id,
                Collateral.run_id == simulation.current_run_id,
                Collateral.status == CollateralStatus.LOCKED,
            )
        ).all()
        active_event = db.scalar(select(StochasticEvent).where(
            StochasticEvent.run_id == simulation.current_run_id,
            StochasticEvent.provider_id == provider.id,
            StochasticEvent.start_time <= simulation.current_time,
            StochasticEvent.end_time > simulation.current_time,
        ).order_by(StochasticEvent.severity.desc(), StochasticEvent.id.desc()))
        result.append(
            {
                **ProviderOut.model_validate(provider).model_dump(exclude={
                    "current_state", "latest_prediction", "locked_collateral", "active_contracts",
                    "future_commitment_cpu", "future_commitment_ram",
                }),
                "locked_collateral": round(sum(item.amount for item in locked_collateral), 2),
                "active_contracts": sum(item.status == ContractStatus.ACTIVE for item in commitments),
                "future_commitment_cpu": round(sum(item.cpu_amount for item in commitments), 2),
                "future_commitment_ram": round(sum(item.ram_amount for item in commitments), 2),
                "current_state": state,
                "latest_prediction": prediction_payload(prediction) if prediction else None,
                "personality": personality(provider.name)["label"],
                "current_volatility": state.volatility if state else 0,
                "active_event": active_event.name if active_event else None,
                "capacity_lost_cpu": state.cpu_capacity_lost if state else 0,
                "capacity_lost_ram": state.ram_capacity_lost if state else 0,
            }
        )
    return result


@router.get("/predictions", response_model=list[PredictionOut])
def list_predictions(include_history: bool = False, db: Session = Depends(get_db)):
    run_id = get_or_create_state(db).current_run_id
    query = select(Prediction).where(Prediction.run_id == run_id).options(selectinload(Prediction.provider)).order_by(Prediction.window_start, Prediction.id)
    if not include_history:
        query = query.where(Prediction.superseded.is_(False))
    return [prediction_payload(item) for item in db.scalars(query).all()]


@router.get("/marketplace", response_model=list[MatchSuggestion])
def marketplace(db: Session = Depends(get_db)):
    return [candidate.as_dict() for candidate in current_matches(db)]


@router.post("/matching/run", response_model=list[MatchSuggestion])
def run_matching(db: Session = Depends(get_db)):
    with simulation_mutation(db):
        matches = current_matches(db)
        if matches:
            best = matches[0]
            record_event(
                db,
                "match.selected",
                f"{best.provider_name} → {best.consumer_name} selected with a {best.match_score:g} match score",
                provider_id=best.provider_id,
                details={"score": best.match_score, "prediction_id": best.prediction_id},
            )
        else:
            record_event(db, "match.none", "Matching completed; no feasible predictive match was found", severity="warning")
        db.commit()
        return [candidate.as_dict() for candidate in matches]


@router.get("/contracts", response_model=list[ContractOut])
def list_contracts(db: Session = Depends(get_db)):
    run_id = get_or_create_state(db).current_run_id
    contracts = db.scalars(
        select(BarterContract).where(BarterContract.run_id == run_id)
        .options(
            selectinload(BarterContract.provider),
            selectinload(BarterContract.consumer),
            selectinload(BarterContract.collateral),
        )
        .order_by(BarterContract.id.desc())
    ).all()
    return [contract_payload(item) for item in contracts]


@router.get("/contracts/{contract_id}")
def contract_detail(contract_id: int, db: Session = Depends(get_db)):
    contract = get_contract_or_404(db, contract_id)
    transactions = db.scalars(
        select(CreditTransaction).where(CreditTransaction.contract_id == contract_id).order_by(CreditTransaction.id)
    ).all()
    reputation = db.scalars(
        select(ReputationHistory).where(ReputationHistory.contract_id == contract_id).order_by(ReputationHistory.id)
    ).all()
    renegotiation = db.scalars(
        select(RenegotiationEvent).where(RenegotiationEvent.original_contract_id == contract_id)
    ).all()
    events = db.scalars(select(EventLog).where(EventLog.contract_id == contract_id).order_by(EventLog.id)).all()
    return {
        "contract": contract_payload(contract),
        "transactions": [
            {**CreditTransactionOut.model_validate(item).model_dump(), "provider_name": item.provider.name}
            for item in transactions
        ],
        "reputation_history": [
            {**ReputationHistoryOut.model_validate(item).model_dump(), "provider_name": item.provider.name}
            for item in reputation
        ],
        "renegotiations": [RenegotiationEventOut.model_validate(item) for item in renegotiation],
        "events": [EventOut.model_validate(item) for item in events],
    }


@router.post("/contracts", response_model=ContractOut, status_code=201)
def create_contract_endpoint(payload: CreateContractRequest, db: Session = Depends(get_db)):
    with simulation_mutation(db):
        contract = create_contract(db, **payload.model_dump())
        return contract_payload(get_contract_or_404(db, contract.id))


@router.post("/contracts/{contract_id}/start", response_model=ContractOut)
def start_contract(contract_id: int, db: Session = Depends(get_db)):
    with simulation_mutation(db):
        contract = transition_to_active(db, get_contract_or_404(db, contract_id))
        return contract_payload(get_contract_or_404(db, contract.id))


@router.post("/contracts/{contract_id}/complete", response_model=ContractOut)
def complete_contract_endpoint(contract_id: int, payload: SettlementRequest, db: Session = Depends(get_db)):
    with simulation_mutation(db):
        contract = complete_contract(db, get_contract_or_404(db, contract_id), **payload.model_dump())
        return contract_payload(get_contract_or_404(db, contract.id))


@router.post("/contracts/{contract_id}/fail", response_model=ContractOut)
def fail_contract_endpoint(contract_id: int, db: Session = Depends(get_db)):
    with simulation_mutation(db):
        contract = fail_contract(db, get_contract_or_404(db, contract_id))
        return contract_payload(get_contract_or_404(db, contract.id))


@router.get("/credit-transactions", response_model=list[CreditTransactionOut])
def list_credit_transactions(db: Session = Depends(get_db)):
    run_id = get_or_create_state(db).current_run_id
    items = db.scalars(
        select(CreditTransaction).where(CreditTransaction.run_id == run_id).options(selectinload(CreditTransaction.provider)).order_by(CreditTransaction.id.desc())
    ).all()
    return [
        {**CreditTransactionOut.model_validate(item).model_dump(), "provider_name": item.provider.name}
        for item in items
    ]


@router.get("/reputation-history", response_model=list[ReputationHistoryOut])
def reputation_history(db: Session = Depends(get_db)):
    run_id = get_or_create_state(db).current_run_id
    items = db.scalars(
        select(ReputationHistory).where(ReputationHistory.run_id == run_id).options(selectinload(ReputationHistory.provider)).order_by(ReputationHistory.id.desc())
    ).all()
    return [
        {**ReputationHistoryOut.model_validate(item).model_dump(), "provider_name": item.provider.name}
        for item in items
    ]


@router.get("/renegotiations", response_model=list[RenegotiationEventOut])
def renegotiations(db: Session = Depends(get_db)):
    run_id = get_or_create_state(db).current_run_id
    return db.scalars(select(RenegotiationEvent).where(RenegotiationEvent.run_id == run_id).order_by(RenegotiationEvent.id.desc())).all()


@router.get("/events", response_model=list[EventOut])
def events(
    limit: int = Query(default=100, ge=1, le=500),
    provider_id: int | None = None,
    event_type: str | None = None,
    contract_id: int | None = None,
    severity: str | None = None,
    db: Session = Depends(get_db),
):
    run_id = get_or_create_state(db).current_run_id
    query = select(EventLog).where(EventLog.run_id == run_id)
    if provider_id is not None:
        query = query.where(EventLog.provider_id == provider_id)
    if event_type:
        query = query.where(EventLog.event_type.contains(event_type))
    if contract_id is not None:
        query = query.where(EventLog.contract_id == contract_id)
    if severity:
        query = query.where(EventLog.severity == severity)
    return db.scalars(query.order_by(EventLog.id.desc()).limit(limit)).all()


@router.post("/simulation/reset", response_model=ActionResponse)
def reset(db: Session = Depends(get_db)):
    state = reset_simulation(db)
    return ActionResponse(message=f"Simulation run #{state.current_run_id} restarted with seed {state.seed}")


@router.post("/simulation/generate-predictions", response_model=ActionResponse)
def generate_predictions(db: Session = Depends(get_db)):
    with simulation_mutation(db):
        predictions = generate_initial_predictions(db)
        return ActionResponse(message=f"Generated {len(predictions)} upcoming predictions")


@router.post("/simulation/re-evaluate", response_model=ActionResponse)
def reevaluate(db: Session = Depends(get_db)):
    with simulation_mutation(db):
        ids = reevaluate_and_renegotiate(db)
        return ActionResponse(message="Predictions re-evaluated and at-risk capacity reassigned", affected_contract_ids=ids)


@router.post("/simulation/start-contracts", response_model=ActionResponse)
def start_contracts(db: Session = Depends(get_db)):
    with simulation_mutation(db):
        run_id = get_or_create_state(db).current_run_id
        contracts = db.scalars(
            select(BarterContract).where(BarterContract.run_id == run_id, BarterContract.status == ContractStatus.SCHEDULED).order_by(BarterContract.id)
        ).all()
        ids = []
        for contract in contracts:
            transition_to_active(db, contract, commit=False)
            ids.append(contract.id)
        db.commit()
        return ActionResponse(message=f"Activated {len(ids)} scheduled contract(s)", affected_contract_ids=ids)


@router.post("/simulation/complete-contracts", response_model=ActionResponse)
def complete_contracts(db: Session = Depends(get_db)):
    with simulation_mutation(db):
        run_id = get_or_create_state(db).current_run_id
        contracts = db.scalars(
            select(BarterContract).where(BarterContract.run_id == run_id, BarterContract.status == ContractStatus.ACTIVE).order_by(BarterContract.id)
        ).all()
        ids = []
        for contract in contracts:
            complete_contract(db, contract, commit=False)
            ids.append(contract.id)
        db.commit()
        return ActionResponse(message=f"Completed and settled {len(ids)} active contract(s)", affected_contract_ids=ids)


@router.post("/simulation/fail-next", response_model=ActionResponse)
def fail_next(db: Session = Depends(get_db)):
    with simulation_mutation(db):
        run_id = get_or_create_state(db).current_run_id
        contract = db.scalar(
            select(BarterContract)
            .where(BarterContract.run_id == run_id, BarterContract.status.in_([ContractStatus.ACTIVE, ContractStatus.SCHEDULED]))
            .order_by(BarterContract.status.desc(), BarterContract.id)
        )
        if not contract:
            raise HTTPException(status_code=409, detail="There is no scheduled or active contract to fail")
        fail_contract(db, contract)
        return ActionResponse(message=f"Simulated failure of contract #{contract.id}", affected_contract_ids=[contract.id])


@router.get("/simulation/state")
def simulation_state(db: Session = Depends(get_db)):
    return state_payload(get_or_create_state(db))


@router.post("/simulation/start")
def simulation_start(db: Session = Depends(get_db)):
    return state_payload(start_simulation(db))


@router.post("/simulation/pause")
def simulation_pause(db: Session = Depends(get_db)):
    return state_payload(pause_simulation(db))


@router.post("/simulation/resume")
def simulation_resume(db: Session = Depends(get_db)):
    return state_payload(start_simulation(db))


@router.patch("/simulation/speed")
def simulation_speed(payload: SimulationSpeedRequest, db: Session = Depends(get_db)):
    return state_payload(set_speed(db, payload.speed))


@router.post("/simulation/step")
def simulation_step(payload: SimulationStepRequest, db: Session = Depends(get_db)):
    return state_payload(step_forward(db, payload.minutes))


@router.put("/simulation/configure")
def simulation_configure(payload: SimulationConfigureRequest, db: Session = Depends(get_db)):
    return state_payload(configure_simulation(db, **payload.model_dump()))


@router.post("/simulation/random-seed")
def simulation_random_seed(db: Session = Depends(get_db)):
    return state_payload(generate_seed_and_restart(db))


@router.post("/simulation/restart-same-seed")
def simulation_restart_same_seed(db: Session = Depends(get_db)):
    return state_payload(restart_same_seed(db))


@router.post("/simulation/events/inject")
def inject_event(payload: InjectEventRequest, db: Session = Depends(get_db)):
    with simulation_mutation(db):
        state = get_or_create_state(db)
        provider = db.get(Provider, payload.provider_id)
        if not provider:
            raise HTTPException(status_code=404, detail="Provider not found")
        if payload.kind == "failure":
            event = inject_failure(db, state, provider, state.current_time, payload.severity)
        else:
            event = inject_workload_event(db, state, provider, state.current_time, payload.kind, payload.severity)
        sample_resources(db, state.current_time)
        db.commit()
        return {"message": f"Injected {event.name} on {provider.name}", "event_id": event.id}


@router.get("/analytics/summary")
def analytics(db: Session = Depends(get_db)):
    return analytics_summary(db)


@router.get("/analytics/credits")
def credit_analytics(db: Session = Depends(get_db)):
    return credit_timelines(db)


@router.get("/simulation/runs")
def simulation_runs(limit: int = Query(default=20, ge=1, le=100), db: Session = Depends(get_db)):
    return list_run_summaries(db, limit)


def _provider_analytics_payload(db: Session, provider_id: int, range_minutes: int) -> dict:
    data = provider_analytics(db, provider_id, range_minutes)
    if data is None:
        raise HTTPException(status_code=404, detail="Provider not found")
    provider_summary = next(item for item in list_providers(db) if item["id"] == provider_id)
    return {
        "provider": provider_summary,
        "resource_history": [ResourceStateOut.model_validate(item).model_dump() for item in data["resource_history"]],
        "predictions": [prediction_payload(item) for item in data["predictions"]],
        "evaluations": [
            {
                "id": item.id,
                "prediction_id": item.prediction_id,
                "simulation_time": item.simulation_time,
                "actual_cpu_usage": item.actual_cpu_usage,
                "actual_ram_usage": item.actual_ram_usage,
                "cpu_absolute_error": item.cpu_absolute_error,
                "ram_absolute_error": item.ram_absolute_error,
                "percentage_error": item.percentage_error,
                "forecast_bias": item.forecast_bias,
                "event_impacted": item.event_impacted,
                "successful": item.successful,
            }
            for item in data["evaluations"]
        ],
        "contracts": [contract_payload(item) for item in data["contracts"]],
        "transactions": [
            {**CreditTransactionOut.model_validate(item).model_dump(), "provider_name": item.provider.name}
            for item in data["transactions"]
        ],
        "reputation_history": [
            {**ReputationHistoryOut.model_validate(item).model_dump(), "provider_name": item.provider.name}
            for item in data["reputation_history"]
        ],
        "future_reservations": [contract_payload(item) for item in data["future_reservations"]],
        "forecast_metrics": data["forecast_metrics"],
        "current_volatility": data["current_volatility"],
        "active_stochastic_events": [stochastic_event_payload(item) for item in data["active_stochastic_events"]],
        "stochastic_events": [stochastic_event_payload(item) for item in data["stochastic_events"]],
        "historical_failures": [stochastic_event_payload(item) for item in data["historical_failures"]],
        "emergency_contracts": data["emergency_contracts"],
        "predictive_contracts": data["predictive_contracts"],
    }


def stochastic_event_payload(item: StochasticEvent) -> dict:
    return {
        "id": item.id, "run_id": item.run_id, "provider_id": item.provider_id,
        "provider_name": item.provider.name, "event_type": item.event_type, "name": item.name,
        "affected_resource": item.affected_resource, "start_time": item.start_time, "end_time": item.end_time,
        "magnitude_percent": item.magnitude_percent, "capacity_loss_percent": item.capacity_loss_percent,
        "severity": item.severity, "source": item.source, "active": item.active, "details": item.details,
    }


@router.get("/providers/{provider_id}/analytics")
def provider_analytics_endpoint(
    provider_id: int,
    range_minutes: int = Query(default=360, ge=30, le=1440),
    db: Session = Depends(get_db),
):
    return _provider_analytics_payload(db, provider_id, range_minutes)


@router.get("/simulation/snapshot")
def simulation_snapshot(
    provider_id: int | None = None,
    range_minutes: int = Query(default=360, ge=30, le=1440),
    db: Session = Depends(get_db),
):
    simulation = get_or_create_state(db)
    run_id = simulation.current_run_id
    providers = list_providers(db)
    provider_ids = {item["id"] for item in providers}
    selected_id = provider_id if provider_id in provider_ids else (providers[0]["id"] if providers else None)
    return {
        "simulation": state_payload(simulation),
        "providers": providers,
        "predictions": list_predictions(False, db),
        "contracts": list_contracts(db),
        "events": [EventOut.model_validate(item).model_dump() for item in db.scalars(
            select(EventLog).where(EventLog.run_id == run_id).order_by(EventLog.id.desc()).limit(120)
        ).all()],
        "analytics": analytics_summary(db),
        "matches": [candidate.as_dict() for candidate in current_matches(db)],
        "transactions": [
            {**CreditTransactionOut.model_validate(item).model_dump(), "provider_name": item.provider.name}
            for item in db.scalars(
                select(CreditTransaction).where(CreditTransaction.run_id == run_id).options(selectinload(CreditTransaction.provider)).order_by(CreditTransaction.id.desc()).limit(120)
            ).all()
        ],
        "reputation": [
            {**ReputationHistoryOut.model_validate(item).model_dump(), "provider_name": item.provider.name}
            for item in db.scalars(
                select(ReputationHistory).where(ReputationHistory.run_id == run_id).options(selectinload(ReputationHistory.provider)).order_by(ReputationHistory.id.desc()).limit(120)
            ).all()
        ],
        "renegotiations": [
            RenegotiationEventOut.model_validate(item).model_dump()
            for item in db.scalars(select(RenegotiationEvent).where(RenegotiationEvent.run_id == run_id).order_by(RenegotiationEvent.id.desc()).limit(80)).all()
        ],
        "credit_timelines": credit_timelines(db),
        "stochastic_events": [stochastic_event_payload(item) for item in db.scalars(
            select(StochasticEvent).where(StochasticEvent.run_id == run_id).order_by(StochasticEvent.start_time.desc()).limit(200)
        ).all()],
        "shortages": [{
            "id": item.id, "provider_id": item.provider_id, "provider_name": item.provider.name,
            "detected_at": item.detected_at, "cpu_deficit": item.cpu_deficit, "ram_deficit": item.ram_deficit,
            "resolution_type": item.resolution_type, "outcome": item.outcome, "contract_ids": item.contract_ids,
            "resolved_at": item.resolved_at, "reaction_time_minutes": item.reaction_time_minutes, "details": item.details,
        } for item in db.scalars(select(ShortageEvent).where(
            ShortageEvent.run_id == run_id,
        ).order_by(ShortageEvent.detected_at.desc()).limit(100)).all()],
        "selected_provider": _provider_analytics_payload(db, selected_id, range_minutes) if selected_id else None,
    }
