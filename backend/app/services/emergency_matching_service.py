"""Reactive shortage recovery using current observations, not future truth."""

from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    BarterContract,
    ContractStatus,
    Provider,
    RenegotiationEvent,
    ResourceState,
    ShortageEvent,
    SimulationState,
)
from .contract_service import create_contract, fail_contract, transition_to_active
from .credit_service import release_collateral
from .event_service import record_event

OPEN = [ContractStatus.PROPOSED, ContractStatus.SCHEDULED, ContractStatus.AT_RISK, ContractStatus.ACTIVE]


def _state_at(db: Session, run_id: int, provider_id: int, now: datetime) -> ResourceState | None:
    return db.scalar(select(ResourceState).where(
        ResourceState.run_id == run_id,
        ResourceState.provider_id == provider_id,
        ResourceState.simulation_time <= now,
    ).order_by(ResourceState.simulation_time.desc(), ResourceState.id.desc()))


def _incoming(db: Session, run_id: int, consumer_id: int, now: datetime, barter_type: str | None = None) -> tuple[float, float]:
    query = select(BarterContract).where(
        BarterContract.run_id == run_id,
        BarterContract.consumer_id == consumer_id,
        BarterContract.status.in_([ContractStatus.SCHEDULED, ContractStatus.ACTIVE]),
        BarterContract.start_time <= now,
        BarterContract.end_time > now,
    )
    if barter_type:
        query = query.where(BarterContract.barter_type == barter_type)
    items = db.scalars(query).all()
    return sum(item.cpu_amount for item in items), sum(item.ram_amount for item in items)


def _allocate_emergency(
    db: Session,
    state: SimulationState,
    consumer: Provider,
    now: datetime,
    cpu_needed: float,
    ram_needed: float,
    *,
    end_time: datetime | None = None,
    parent_contract_id: int | None = None,
    reason: str,
) -> tuple[list[int], float, float]:
    candidates: list[tuple[Provider, ResourceState, float]] = []
    for provider in db.scalars(select(Provider).where(Provider.id != consumer.id).order_by(Provider.id)).all():
        current = _state_at(db, state.current_run_id, provider.id, now)
        if not current or current.usable_cpu <= 0 or current.usable_ram <= 0:
            continue
        safety = max(0.45, min(0.88, provider.forecast_reliability / 100 - current.volatility / 100))
        candidates.append((provider, current, safety))
    candidates.sort(key=lambda item: (item[0].sla_reputation + item[0].forecast_reliability + item[1].cpu_available, item[0].name), reverse=True)
    remaining_cpu, remaining_ram = cpu_needed, ram_needed
    ids: list[int] = []
    for provider, current, safety in candidates:
        cpu = min(remaining_cpu, max(0, current.effective_future_cpu * safety))
        ram = min(remaining_ram, max(0, current.effective_future_ram * safety))
        if cpu <= 0.01 and ram <= 0.01:
            continue
        try:
            contract = create_contract(
                db,
                provider_id=provider.id,
                consumer_id=consumer.id,
                prediction_id=None,
                cpu_amount=round(cpu, 2),
                ram_amount=round(ram, 2),
                start_time=now,
                end_time=end_time or now + timedelta(minutes=30),
                match_score=round((provider.sla_reputation + provider.forecast_reliability + safety * 100) / 3, 1),
                selection_reason=f"Emergency current-capacity match: {reason}",
                parent_contract_id=parent_contract_id,
                simulation_time=now,
                barter_type="Emergency",
                emergency_reason=reason,
                reaction_time_minutes=0,
                commit=False,
            )
        except HTTPException:
            continue
        transition_to_active(db, contract, simulation_time=now, commit=False)
        ids.append(contract.id)
        remaining_cpu = max(0, remaining_cpu - cpu)
        remaining_ram = max(0, remaining_ram - ram)
        record_event(
            db, "emergency.provider_selected",
            f"{provider.name} immediately supplied {cpu:.1f} CPU / {ram:.1f} GB to {consumer.name}",
            provider_id=provider.id, contract_id=contract.id, simulation_time=now,
            details={"consumer_id": consumer.id, "reaction_time_minutes": 0},
        )
        if remaining_cpu <= 0.01 and remaining_ram <= 0.01:
            break
    return ids, round(remaining_cpu, 2), round(remaining_ram, 2)


def process_current_shortages(db: Session, now: datetime) -> None:
    state = db.get(SimulationState, 1)
    if not state or not state.current_run_id:
        return
    for provider in db.scalars(select(Provider).order_by(Provider.id)).all():
        current = _state_at(db, state.current_run_id, provider.id, now)
        if not current:
            continue
        raw_cpu = max(0, current.cpu_usage - current.usable_cpu)
        raw_ram = max(0, current.ram_usage - current.usable_ram)
        if raw_cpu <= state.configuration.get("emergency_threshold", 2) and raw_ram <= state.configuration.get("emergency_threshold", 2):
            continue
        recent = db.scalar(select(ShortageEvent).where(
            ShortageEvent.run_id == state.current_run_id,
            ShortageEvent.provider_id == provider.id,
            ShortageEvent.detected_at >= now - timedelta(minutes=30),
        ).order_by(ShortageEvent.detected_at.desc()))
        if recent:
            continue
        predictive_cpu, predictive_ram = _incoming(db, state.current_run_id, provider.id, now, "Predictive")
        if predictive_cpu + 0.01 >= raw_cpu and predictive_ram + 0.01 >= raw_ram:
            shortage = ShortageEvent(
                run_id=state.current_run_id, provider_id=provider.id, detected_at=now,
                cpu_deficit=round(raw_cpu, 2), ram_deficit=round(raw_ram, 2),
                resolution_type="Predictive", outcome="Prevented", resolved_at=now, reaction_time_minutes=0,
                details={"predictive_cpu": predictive_cpu, "predictive_ram": predictive_ram},
            )
            db.add(shortage)
            record_event(
                db, "shortage.prevented", f"Predictive barter prevented {provider.name}'s live shortage",
                provider_id=provider.id, simulation_time=now, details={"cpu_deficit": raw_cpu, "ram_deficit": raw_ram},
            )
            continue
        emergency_cpu, emergency_ram = _incoming(db, state.current_run_id, provider.id, now, "Emergency")
        cpu_needed = max(0, raw_cpu - predictive_cpu - emergency_cpu)
        ram_needed = max(0, raw_ram - predictive_ram - emergency_ram)
        record_event(
            db, "emergency.initiated",
            f"Emergency barter initiated for {provider.name}: current deficit {cpu_needed:.1f} CPU / {ram_needed:.1f} GB",
            severity="warning", provider_id=provider.id, simulation_time=now,
        )
        ids, remaining_cpu, remaining_ram = _allocate_emergency(
            db, state, provider, now, cpu_needed, ram_needed, reason="Unexpected current workload shortage",
        )
        recovered = remaining_cpu <= 0.01 and remaining_ram <= 0.01
        shortage = ShortageEvent(
            run_id=state.current_run_id, provider_id=provider.id, detected_at=now,
            cpu_deficit=round(raw_cpu, 2), ram_deficit=round(raw_ram, 2),
            resolution_type="Emergency" if recovered else "Unresolved",
            outcome="Recovered" if recovered else "Unresolved", contract_ids=ids,
            resolved_at=now if recovered else None, reaction_time_minutes=0 if recovered else None,
            details={"remaining_cpu": remaining_cpu, "remaining_ram": remaining_ram},
        )
        db.add(shortage)
        record_event(
            db, "emergency.recovered" if recovered else "shortage.unresolved",
            f"{provider.name} {'recovered through emergency barter' if recovered else 'still has an unresolved shortage'}",
            severity="info" if recovered else "error", provider_id=provider.id, simulation_time=now,
            details={"contract_ids": ids, "remaining_cpu": remaining_cpu, "remaining_ram": remaining_ram},
        )


def react_to_failed_commitments(db: Session, now: datetime) -> None:
    state = db.get(SimulationState, 1)
    if not state:
        return
    contracts = db.scalars(select(BarterContract).where(
        BarterContract.run_id == state.current_run_id,
        BarterContract.status == ContractStatus.ACTIVE,
        BarterContract.end_time > now,
    ).order_by(BarterContract.id)).all()
    for contract in contracts:
        current = _state_at(db, state.current_run_id, contract.provider_id, now)
        if not current or (current.cpu_capacity_lost <= 0 and current.ram_capacity_lost <= 0):
            continue
        missing_cpu = max(0, contract.cpu_amount - current.cpu_available)
        missing_ram = max(0, contract.ram_amount - current.ram_available)
        if missing_cpu <= 0.01 and missing_ram <= 0.01:
            continue
        record_event(
            db, "contract.at_risk", f"Active contract #{contract.id} at risk after {contract.provider.name} lost capacity",
            severity="error", provider_id=contract.provider_id, contract_id=contract.id, simulation_time=now,
            details={"missing_cpu": missing_cpu, "missing_ram": missing_ram, "failure_driven": True},
        )
        ids, remaining_cpu, remaining_ram = _allocate_emergency(
            db, state, contract.consumer, now, missing_cpu, missing_ram,
            end_time=contract.end_time, parent_contract_id=contract.id,
            reason=f"Emergency replacement for impaired contract #{contract.id}",
        )
        if remaining_cpu <= 0.01 and remaining_ram <= 0.01:
            release_collateral(db, contract, "Replaced after live capacity failure", now)
            contract.status = ContractStatus.RENEGOTIATED
            db.add(RenegotiationEvent(
                run_id=state.current_run_id, original_contract_id=contract.id,
                reason="Live provider capacity failure", old_cpu=contract.cpu_amount, old_ram=contract.ram_amount,
                retained_cpu=max(0, contract.cpu_amount - missing_cpu), retained_ram=max(0, contract.ram_amount - missing_ram),
                replacement_contract_ids=ids, simulation_time=now,
            ))
            record_event(
                db, "contract.renegotiated", f"Contract #{contract.id} migrated to {len(ids)} emergency replacement provider(s)",
                provider_id=contract.provider_id, contract_id=contract.id, simulation_time=now,
                details={"replacement_contract_ids": ids, "failure_driven": True},
            )
        else:
            fail_contract(db, contract, simulation_time=now, commit=False)

