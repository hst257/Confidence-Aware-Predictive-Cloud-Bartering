"""Rolling, interval-aware advance allocation using persisted forecasts only."""

from datetime import datetime
from math import floor

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Prediction, Provider, ResourceState, SimulationState
from .contract_service import create_contract
from .credit_service import available_credit
from .event_service import record_event
from .matching_service import collateral_cost, resource_cost, score_capacity_match
from .reservation_service import overlaps, peak, segments


def _units(value: float) -> float:
    return floor(max(0, value) * 100 + 1e-8) / 100


def auto_match_and_create(db: Session, cycle_id: str, simulation_time: datetime) -> list[int]:
    state = db.get(SimulationState, 1)
    if not state or not state.current_run_id:
        return []
    predictions = list(db.scalars(select(Prediction).where(
        Prediction.run_id == state.current_run_id, Prediction.cycle_id == cycle_id,
        Prediction.superseded.is_(False), Prediction.window_start > simulation_time,
    ).order_by(Prediction.window_start, Prediction.provider_id)).all())
    providers = {item.id: item for item in db.scalars(select(Provider)).all()}
    current = {provider_id: db.scalar(select(ResourceState).where(
        ResourceState.run_id == state.current_run_id, ResourceState.provider_id == provider_id,
        ResourceState.simulation_time <= simulation_time,
    ).order_by(ResourceState.simulation_time.desc(), ResourceState.id.desc())) for provider_id in providers}
    created = []
    for demand in predictions:
        if demand.cpu_deficit <= 0.01 and demand.ram_deficit <= 0.01:
            continue
        consumer = providers[demand.provider_id]
        incoming = overlaps(db, state.current_run_id, consumer.id, demand.window_start, demand.window_end, incoming=True)
        # Coverage is local to each half-open interval, not a global cooldown.
        for start, end, cpu_covered, ram_covered in segments(incoming, demand.window_start, demand.window_end):
            duration_factor = (end - start).total_seconds() / 3600
            cpu_needed = _units(demand.cpu_deficit - cpu_covered)
            ram_needed = _units(demand.ram_deficit - ram_covered)
            if cpu_needed <= 0.01 and ram_needed <= 0.01:
                continue
            if round(resource_cost(cpu_needed, ram_needed) * duration_factor, 2) > available_credit(db, consumer, state.current_run_id):
                continue
            candidates = []
            for supply in predictions:
                if supply.provider_id == consumer.id or supply.window_start > start or supply.window_end < end:
                    continue
                provider = providers[supply.provider_id]
                cpu_reserved, ram_reserved = peak(overlaps(db, state.current_run_id, provider.id, start, end), start, end)
                cpu = max(0, supply.safe_cpu_commitment - cpu_reserved)
                ram = max(0, supply.safe_ram_commitment - ram_reserved)
                observation = current[provider.id]
                if observation and observation.cpu_capacity_lost > 0:
                    cpu = min(cpu, max(0, observation.cpu_available - cpu_reserved))
                if observation and observation.ram_capacity_lost > 0:
                    ram = min(ram, max(0, observation.ram_available - ram_reserved))
                cpu, ram = min(cpu_needed, cpu), min(ram_needed, ram)
                score = score_capacity_match(provider, supply.confidence,
                    cpu / cpu_needed if cpu_needed else 1, ram / ram_needed if ram_needed else 1)
                candidates.append((score, provider.name, supply, cpu, ram))
            candidates.sort(key=lambda item: (-item[0], item[1], item[2].id))
            remaining_cpu, remaining_ram = cpu_needed, ram_needed
            plan = []
            used_providers = set()
            for score, _, supply, cpu, ram in candidates:
                # Overlapping forecasts must not count one supplier twice.
                if supply.provider_id in used_providers:
                    continue
                cpu, ram = min(remaining_cpu, cpu), min(remaining_ram, ram)
                collateral = collateral_cost(round(resource_cost(cpu, ram) * duration_factor, 2))
                credit = available_credit(db, providers[supply.provider_id], state.current_run_id)
                if collateral > credit:
                    factor = max(0, credit) / collateral
                    cpu, ram = cpu * factor, ram * factor
                cpu, ram = _units(cpu), _units(ram)
                if cpu <= 0.01 and ram <= 0.01:
                    continue
                plan.append((supply, cpu, ram, score))
                used_providers.add(supply.provider_id)
                remaining_cpu, remaining_ram = max(0, remaining_cpu - cpu), max(0, remaining_ram - ram)
                if remaining_cpu <= 0.01 and remaining_ram <= 0.01:
                    break
            if remaining_cpu > 0.01 or remaining_ram > 0.01:
                continue
            planned_ids = []
            try:
                # A failed pooled plan leaves no partial contract or collateral.
                with db.begin_nested():
                    for supply, cpu, ram, score in plan:
                        contract = create_contract(db,
                            provider_id=supply.provider_id, consumer_id=consumer.id, prediction_id=supply.id,
                            cpu_amount=cpu, ram_amount=ram, start_time=start, end_time=end,
                            match_score=score, simulation_time=simulation_time, commit=False, prorate=True,
                            selection_reason=(f"Proactive pooled allocation for {consumer.name}; "
                                f"{(start - simulation_time).total_seconds() / 60:g} minutes ahead. "
                                f"Covers uncovered interval {start:%H:%M}–{end:%H:%M}; "
                                f"{supply.confidence:g}% supplier confidence; {len(plan)} supplier(s)."))
                        planned_ids.append(contract.id)
                    db.flush()
            except HTTPException as exc:
                if exc.status_code != 409:
                    raise
                continue
            created.extend(planned_ids)
            record_event(db, "match.selected",
                f"Reserved {cpu_needed:g} CPU / {ram_needed:g} GB for {consumer.name} before {start:%H:%M}",
                provider_id=consumer.id, simulation_time=simulation_time,
                details={"cycle_id": cycle_id, "demand_prediction_id": demand.id,
                    "contract_ids": planned_ids, "lead_minutes": (start - simulation_time).total_seconds() / 60})
    return created
