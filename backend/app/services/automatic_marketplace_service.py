from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import BarterContract, ContractStatus, SimulationState
from .contract_service import create_contract
from .event_service import record_event
from .matching_service import find_matches


OPEN_STATUSES = [ContractStatus.PROPOSED, ContractStatus.SCHEDULED, ContractStatus.AT_RISK, ContractStatus.ACTIVE]


def auto_match_and_create(db: Session, cycle_id: str, simulation_time: datetime) -> list[int]:
    """React to forecasts using business services; the engine owns no market rules."""
    settings = get_settings()
    state = db.get(SimulationState, 1)
    if state.bartering_strategy == "Reactive Only":
        return []
    candidates = [
        item for item in find_matches(db, cycle_id=cycle_id)
        if item.horizon_minutes == settings.planning_horizon_minutes
    ]
    created: list[int] = []
    handled_consumers: set[int] = set()
    cooldown = timedelta(minutes=settings.contract_planning_cooldown_minutes)
    for candidate in candidates:
        if candidate.consumer_id in handled_consumers:
            continue
        existing = db.scalars(
            select(BarterContract).where(
                BarterContract.run_id == state.current_run_id,
                BarterContract.consumer_id == candidate.consumer_id,
                BarterContract.status.in_(OPEN_STATUSES),
            )
        ).all()
        if any(abs(contract.start_time - candidate.window_start) < cooldown for contract in existing):
            handled_consumers.add(candidate.consumer_id)
            continue
        # Phase 2 avoids intentionally under-covered contracts. A later cycle can
        # retry if no single safe supplier can cover both resource dimensions.
        if candidate.cpu_amount + 0.01 < candidate.requested_cpu or candidate.ram_amount + 0.01 < candidate.requested_ram:
            continue
        record_event(
            db,
            "match.selected",
            f"{candidate.provider_name} selected for {candidate.consumer_name} with score {candidate.match_score:g}",
            provider_id=candidate.provider_id,
            simulation_time=simulation_time,
            details={
                "score": candidate.match_score,
                "safe_cpu": candidate.safe_cpu_available,
                "reserved_cpu": candidate.reserved_cpu,
                "cycle_id": cycle_id,
            },
        )
        contract = create_contract(
            db,
            provider_id=candidate.provider_id,
            consumer_id=candidate.consumer_id,
            prediction_id=candidate.prediction_id,
            cpu_amount=candidate.cpu_amount,
            ram_amount=candidate.ram_amount,
            start_time=candidate.window_start,
            end_time=candidate.window_end,
            match_score=candidate.match_score,
            selection_reason="Automatically selected. " + candidate.selection_reason,
            simulation_time=simulation_time,
            commit=False,
        )
        created.append(contract.id)
        handled_consumers.add(candidate.consumer_id)
    return created
