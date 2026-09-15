from sqlalchemy.orm import Session
from datetime import datetime

from ..models import EventLog, SimulationState


def record_event(
    db: Session,
    event_type: str,
    message: str,
    *,
    severity: str = "info",
    provider_id: int | None = None,
    contract_id: int | None = None,
    details: dict | None = None,
    simulation_time: datetime | None = None,
) -> EventLog:
    state = db.get(SimulationState, 1)
    event = EventLog(
        run_id=state.current_run_id if state else None,
        event_type=event_type,
        severity=severity,
        message=message,
        provider_id=provider_id,
        contract_id=contract_id,
        details=details or {},
        simulation_time=simulation_time,
    )
    db.add(event)
    db.flush()
    return event
