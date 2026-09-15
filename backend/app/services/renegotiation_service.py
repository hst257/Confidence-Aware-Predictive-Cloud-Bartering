from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import BarterContract, ContractStatus, Prediction, Provider, RenegotiationEvent, SimulationState
from ..simulation.prediction_generator import generate_revised_cloud_b_prediction
from .contract_service import create_contract
from .credit_service import release_collateral
from .event_service import record_event


def _other_commitments(db: Session, contract: BarterContract) -> tuple[float, float]:
    items = db.scalars(
        select(BarterContract).where(
            BarterContract.provider_id == contract.provider_id,
            BarterContract.run_id == contract.run_id,
            BarterContract.id != contract.id,
            BarterContract.status.in_([
                ContractStatus.PROPOSED,
                ContractStatus.SCHEDULED,
                ContractStatus.AT_RISK,
                ContractStatus.ACTIVE,
            ]),
            BarterContract.start_time < contract.end_time,
            BarterContract.end_time > contract.start_time,
        )
    ).all()
    return sum(item.cpu_amount for item in items), sum(item.ram_amount for item in items)


def monitor_contract_risk(db: Session, simulation_time) -> list[int]:
    """Reforecast open commitments and split any unsafe agreement."""
    changed: list[int] = []
    state = db.get(SimulationState, 1)
    if state.bartering_strategy == "Reactive Only":
        return []
    contracts = db.scalars(
        select(BarterContract).where(
            BarterContract.run_id == state.current_run_id,
            BarterContract.status.in_([ContractStatus.SCHEDULED, ContractStatus.AT_RISK]),
            BarterContract.start_time > simulation_time,
        ).order_by(BarterContract.id)
    ).all()
    for contract in contracts:
        prediction = db.scalar(
            select(Prediction).where(
                Prediction.provider_id == contract.provider_id,
                Prediction.run_id == state.current_run_id,
                Prediction.window_start == contract.start_time,
                Prediction.simulation_generated_at <= simulation_time,
                Prediction.decision_forecast.is_(True),
            ).order_by(Prediction.simulation_generated_at.desc(), Prediction.id.desc())
        )
        if not prediction:
            continue
        other_cpu, other_ram = _other_commitments(db, contract)
        available_cpu = max(0, prediction.safe_cpu_commitment - other_cpu)
        available_ram = max(0, prediction.safe_ram_commitment - other_ram)
        if available_cpu + 0.01 >= contract.cpu_amount and available_ram + 0.01 >= contract.ram_amount:
            continue

        first_alert = contract.status != ContractStatus.AT_RISK
        contract.status = ContractStatus.AT_RISK
        if first_alert:
            record_event(
                db,
                "contract.at_risk",
                f"Contract #{contract.id} at risk: safe capacity is {available_cpu:.1f} CPU / {available_ram:.1f} GB",
                severity="warning",
                provider_id=contract.provider_id,
                contract_id=contract.id,
                simulation_time=simulation_time,
            )
            record_event(
                db,
                "renegotiation.started",
                f"Automatic renegotiation started for contract #{contract.id}",
                severity="warning",
                contract_id=contract.id,
                simulation_time=simulation_time,
            )

        retained_cpu = min(contract.cpu_amount, available_cpu)
        retained_ram = min(contract.ram_amount, available_ram)
        missing_cpu = max(0, contract.cpu_amount - retained_cpu)
        missing_ram = max(0, contract.ram_amount - retained_ram)

        supply_predictions = db.scalars(
            select(Prediction).where(
                Prediction.cycle_id == prediction.cycle_id,
                Prediction.window_start == contract.start_time,
                Prediction.provider_id.notin_([contract.provider_id, contract.consumer_id]),
                Prediction.decision_forecast.is_(True),
            )
        ).all()
        providers = {item.id: item for item in db.scalars(select(Provider)).all()}
        supply_predictions.sort(
            key=lambda item: (
                item.confidence * 0.35
                + providers[item.provider_id].forecast_reliability * 0.35
                + providers[item.provider_id].sla_reputation * 0.30
            ),
            reverse=True,
        )
        plan: list[tuple[Prediction, float, float]] = []
        remaining_cpu, remaining_ram = missing_cpu, missing_ram
        for supply in supply_predictions:
            dummy = BarterContract(
                id=-1,
                provider_id=supply.provider_id,
                consumer_id=contract.consumer_id,
                cpu_amount=0,
                ram_amount=0,
                start_time=contract.start_time,
                end_time=contract.end_time,
                barter_cost=0,
                prediction_confidence=supply.confidence,
                status=ContractStatus.SCHEDULED,
                match_score=0,
                selection_reason="",
            )
            other_supply_cpu, other_supply_ram = _other_commitments(db, dummy)
            safe_cpu = max(0, supply.safe_cpu_commitment - other_supply_cpu)
            safe_ram = max(0, supply.safe_ram_commitment - other_supply_ram)
            allocation_cpu = min(remaining_cpu, safe_cpu)
            allocation_ram = min(remaining_ram, safe_ram)
            if allocation_cpu > 0 or allocation_ram > 0:
                plan.append((supply, allocation_cpu, allocation_ram))
                remaining_cpu -= allocation_cpu
                remaining_ram -= allocation_ram
            if remaining_cpu <= 0.01 and remaining_ram <= 0.01:
                break
        if remaining_cpu > 0.01 or remaining_ram > 0.01:
            continue

        release_collateral(db, contract, "Replaced after automatic risk detection", simulation_time)
        contract.status = ContractStatus.RENEGOTIATED
        replacement_ids: list[int] = []
        if retained_cpu > 0 or retained_ram > 0:
            retained = create_contract(
                db,
                provider_id=contract.provider_id,
                consumer_id=contract.consumer_id,
                prediction_id=prediction.id,
                cpu_amount=retained_cpu,
                ram_amount=retained_ram,
                start_time=contract.start_time,
                end_time=contract.end_time,
                match_score=round(contract.match_score * 0.9, 1),
                selection_reason="Retained safe portion after an automatic forecast revision.",
                parent_contract_id=contract.id,
                simulation_time=simulation_time,
                commit=False,
            )
            replacement_ids.append(retained.id)
        for supply, cpu, ram in plan:
            provider = providers[supply.provider_id]
            backup = create_contract(
                db,
                provider_id=provider.id,
                consumer_id=contract.consumer_id,
                prediction_id=supply.id,
                cpu_amount=cpu,
                ram_amount=ram,
                start_time=contract.start_time,
                end_time=contract.end_time,
                match_score=round((supply.confidence + provider.forecast_reliability + provider.sla_reputation) / 3, 1),
                selection_reason=(
                    f"Automatic backup: {provider.name} covers {cpu:.1f} CPU / {ram:.1f} GB with "
                    f"{supply.confidence:g}% confidence."
                ),
                parent_contract_id=contract.id,
                simulation_time=simulation_time,
                commit=False,
            )
            replacement_ids.append(backup.id)
            record_event(
                db,
                "renegotiation.backup_selected",
                f"{provider.name} selected as backup for contract #{contract.id}",
                provider_id=provider.id,
                contract_id=contract.id,
                simulation_time=simulation_time,
            )
        db.add(
            RenegotiationEvent(
                run_id=contract.run_id,
                original_contract_id=contract.id,
                reason="Latest forecast reduced safe future capacity",
                old_cpu=contract.cpu_amount,
                old_ram=contract.ram_amount,
                retained_cpu=retained_cpu,
                retained_ram=retained_ram,
                replacement_contract_ids=replacement_ids,
                simulation_time=simulation_time,
            )
        )
        record_event(
            db,
            "contract.renegotiated",
            f"Contract #{contract.id} automatically split into {len(replacement_ids)} safe commitments",
            provider_id=contract.provider_id,
            contract_id=contract.id,
            simulation_time=simulation_time,
            details={"replacement_contract_ids": replacement_ids},
        )
        changed.extend(replacement_ids)
    return changed


def reevaluate_and_renegotiate(db: Session) -> list[int]:
    try:
        revised = generate_revised_cloud_b_prediction(db)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    original = db.scalar(
        select(BarterContract)
        .where(
            BarterContract.provider_id == revised.provider_id,
            BarterContract.run_id == revised.run_id,
            BarterContract.parent_contract_id.is_(None),
            BarterContract.status == ContractStatus.SCHEDULED,
        )
        .order_by(BarterContract.id)
    )
    if not original:
        existing = db.scalar(
            select(RenegotiationEvent).where(RenegotiationEvent.run_id == revised.run_id).order_by(RenegotiationEvent.id.desc())
        )
        if existing:
            db.commit()
            return existing.replacement_contract_ids
        db.commit()
        raise HTTPException(status_code=409, detail="Create the Cloud B contract before re-evaluating")

    retained_cpu = min(original.cpu_amount, revised.predicted_cpu_spare)
    retained_ram = min(original.ram_amount, revised.predicted_ram_spare)
    missing_cpu = round(original.cpu_amount - retained_cpu, 2)
    missing_ram = round(original.ram_amount - retained_ram, 2)
    if missing_cpu <= 0 and missing_ram <= 0:
        db.commit()
        return [original.id]

    record_event(
        db,
        "contract.at_risk",
        f"Contract #{original.id} is at risk: {original.provider.name} is short {missing_cpu:g} CPU / {missing_ram:g} GB",
        severity="warning",
        provider_id=original.provider_id,
        contract_id=original.id,
    )
    original.status = ContractStatus.RENEGOTIATED
    release_collateral(db, original, "Original contract replaced before execution")
    db.flush()

    replacements: list[int] = []
    if retained_cpu > 0 or retained_ram > 0:
        retained = create_contract(
            db,
            provider_id=original.provider_id,
            consumer_id=original.consumer_id,
            prediction_id=revised.id,
            cpu_amount=retained_cpu,
            ram_amount=retained_ram,
            start_time=original.start_time,
            end_time=original.end_time,
            match_score=round(original.match_score * 0.92, 1),
            selection_reason="Retained portion after Cloud B's revised capacity forecast.",
            parent_contract_id=original.id,
            commit=False,
        )
        replacements.append(retained.id)

    # Phase 1 uses persisted current predictions, not a simulation-specific shortcut.
    backup = db.scalar(select(Provider).where(Provider.name == "Cloud C"))
    backup_prediction = db.scalar(
        select(Prediction).where(
            Prediction.provider_id == backup.id,
            Prediction.run_id == revised.run_id,
            Prediction.superseded.is_(False),
        )
    )
    if not backup_prediction or backup_prediction.predicted_cpu_spare < missing_cpu or backup_prediction.predicted_ram_spare < missing_ram:
        db.rollback()
        raise HTTPException(status_code=409, detail="No backup provider can cover the revised shortfall")
    backup_contract = create_contract(
        db,
        provider_id=backup.id,
        consumer_id=original.consumer_id,
        prediction_id=backup_prediction.id,
        cpu_amount=missing_cpu,
        ram_amount=missing_ram,
        start_time=original.start_time,
        end_time=original.end_time,
        match_score=84.3,
        selection_reason=(
            f"Selected as backup: covers the missing {missing_cpu:g} CPU / {missing_ram:g} GB with "
            f"{backup_prediction.confidence:g}% confidence and {backup.forecast_reliability:g}% reliability."
        ),
        parent_contract_id=original.id,
        commit=False,
    )
    replacements.append(backup_contract.id)

    event = RenegotiationEvent(
        run_id=original.run_id,
        original_contract_id=original.id,
        reason="Cloud B's revised prediction could no longer cover the full commitment",
        old_cpu=original.cpu_amount,
        old_ram=original.ram_amount,
        retained_cpu=retained_cpu,
        retained_ram=retained_ram,
        replacement_contract_ids=replacements,
    )
    db.add(event)
    record_event(
        db,
        "contract.renegotiated",
        f"Contract #{original.id} split: Cloud B keeps {retained_cpu:g}/{retained_ram:g}; Cloud C supplies {missing_cpu:g}/{missing_ram:g}",
        provider_id=original.provider_id,
        contract_id=original.id,
        details={"replacement_contract_ids": replacements},
    )
    db.commit()
    return replacements
