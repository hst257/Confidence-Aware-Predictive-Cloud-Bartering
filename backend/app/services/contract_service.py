from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import BarterContract, ContractStatus, Prediction, Provider, SimulationState
from .credit_service import available_credit, forfeit_collateral, lock_collateral, settle_success
from .event_service import record_event
from .matching_service import collateral_cost, resource_cost
from .reputation_service import record_failure, settle_reputation


def create_contract(
    db: Session,
    *,
    provider_id: int,
    consumer_id: int,
    prediction_id: int | None,
    cpu_amount: float,
    ram_amount: float,
    start_time: datetime,
    end_time: datetime,
    match_score: float,
    selection_reason: str,
    parent_contract_id: int | None = None,
    commit: bool = True,
    simulation_time: datetime | None = None,
    barter_type: str = "Predictive",
    emergency_reason: str | None = None,
    reaction_time_minutes: float | None = None,
) -> BarterContract:
    provider = db.get(Provider, provider_id)
    consumer = db.get(Provider, consumer_id)
    prediction = db.get(Prediction, prediction_id) if prediction_id else None
    if not provider or not consumer or (prediction_id is not None and not prediction):
        raise HTTPException(status_code=404, detail="Provider, consumer, or prediction not found")
    if provider_id == consumer_id or (prediction and prediction.provider_id != provider_id):
        raise HTTPException(status_code=422, detail="Invalid provider/consumer prediction combination")
    if end_time <= start_time:
        raise HTTPException(status_code=422, detail="Contract end must be after its start")
    cost = resource_cost(cpu_amount, ram_amount)
    state = db.get(SimulationState, 1)
    run_id = prediction.run_id if prediction else (state.current_run_id if state else None)
    if available_credit(db, consumer, run_id) < cost:
        raise HTTPException(status_code=409, detail=f"{consumer.name} has insufficient uncommitted barter credits")
    contract = BarterContract(
        run_id=run_id,
        provider_id=provider_id,
        consumer_id=consumer_id,
        prediction_id=prediction_id,
        parent_contract_id=parent_contract_id,
        cpu_amount=round(cpu_amount, 2),
        ram_amount=round(ram_amount, 2),
        start_time=start_time,
        end_time=end_time,
        barter_cost=cost,
        prediction_confidence=prediction.confidence if prediction else provider.forecast_reliability,
        status=ContractStatus.SCHEDULED,
        match_score=match_score,
        selection_reason=selection_reason,
        created_simulation_time=simulation_time,
        barter_type=barter_type,
        emergency_reason=emergency_reason,
        reaction_time_minutes=reaction_time_minutes,
    )
    db.add(contract)
    db.flush()
    dynamic_confidence = (prediction.confidence if prediction and prediction.simulation_generated_at is not None else None)
    if prediction is None and barter_type == "Emergency":
        dynamic_confidence = provider.forecast_reliability
    lock_collateral(db, contract, collateral_cost(cost, dynamic_confidence), simulation_time)
    record_event(
        db,
        "contract.created",
        f"{barter_type} contract #{contract.id} scheduled: {provider.name} → {consumer.name}, {cpu_amount:g} CPU / {ram_amount:g} GB",
        provider_id=provider.id,
        contract_id=contract.id,
        details={"cost": cost, "parent_contract_id": parent_contract_id, "barter_type": barter_type, "emergency_reason": emergency_reason},
        simulation_time=simulation_time,
    )
    if commit:
        db.commit()
        db.refresh(contract)
    return contract


def transition_to_active(
    db: Session,
    contract: BarterContract,
    *,
    simulation_time: datetime | None = None,
    commit: bool = True,
) -> BarterContract:
    if contract.status != ContractStatus.SCHEDULED:
        raise HTTPException(status_code=409, detail="Only scheduled contracts can be started")
    contract.status = ContractStatus.ACTIVE
    record_event(
        db,
        "contract.activated",
        f"Contract #{contract.id} activated; resources are being delivered",
        provider_id=contract.provider_id,
        contract_id=contract.id,
        simulation_time=simulation_time,
    )
    if commit:
        db.commit()
        db.refresh(contract)
    return contract


def complete_contract(
    db: Session,
    contract: BarterContract,
    actual_cpu_spare: float | None = None,
    actual_ram_spare: float | None = None,
    simulation_time: datetime | None = None,
    commit: bool = True,
) -> BarterContract:
    if contract.status != ContractStatus.ACTIVE:
        raise HTTPException(status_code=409, detail="Only active contracts can be completed")
    predicted = contract.prediction
    actual_cpu = actual_cpu_spare if actual_cpu_spare is not None else max(contract.cpu_amount, (predicted.predicted_cpu_spare if predicted else contract.cpu_amount) - 1)
    actual_ram = actual_ram_spare if actual_ram_spare is not None else max(contract.ram_amount, (predicted.predicted_ram_spare if predicted else contract.ram_amount) - 2)
    contract.actual_cpu_spare = round(actual_cpu, 2)
    contract.actual_ram_spare = round(actual_ram, 2)
    settle_success(db, contract, simulation_time)
    settle_reputation(db, contract, actual_cpu, actual_ram, simulation_time)
    contract.status = ContractStatus.COMPLETED
    record_event(
        db,
        "contract.completed",
        f"Contract #{contract.id} completed; {contract.cpu_amount:g} CPU / {contract.ram_amount:g} GB delivered",
        provider_id=contract.provider_id,
        contract_id=contract.id,
        simulation_time=simulation_time,
    )
    if commit:
        db.commit()
        db.refresh(contract)
    return contract


def fail_contract(
    db: Session,
    contract: BarterContract,
    *,
    simulation_time: datetime | None = None,
    commit: bool = True,
) -> BarterContract:
    if contract.status not in {ContractStatus.SCHEDULED, ContractStatus.AT_RISK, ContractStatus.ACTIVE}:
        raise HTTPException(status_code=409, detail="Only scheduled or active contracts can fail")
    contract.status = ContractStatus.FAILED
    forfeit_collateral(db, contract, simulation_time)
    record_failure(db, contract, simulation_time)
    record_event(
        db,
        "contract.failed",
        f"Contract #{contract.id} failed; consumer compensation and provider penalties applied",
        severity="error",
        provider_id=contract.provider_id,
        contract_id=contract.id,
        simulation_time=simulation_time,
    )
    if commit:
        db.commit()
        db.refresh(contract)
    return contract
