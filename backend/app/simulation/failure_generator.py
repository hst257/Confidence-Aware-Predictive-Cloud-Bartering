"""Seeded partial-capacity failures, independent of contract logic."""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Provider, StochasticEvent
from ..services.event_service import record_event
from .random_manager import choice, uniform
from .workload_profiles import personality

FAILURE_NAMES = ["Compute Node Failure", "Network Failure", "Storage Degradation", "Partial Capacity Loss", "Provider Outage"]
LOSS_LEVELS = [10, 10, 25, 25, 50, 100]


def _active_failure(db: Session, run_id: int, provider_id: int, now: datetime) -> bool:
    return db.scalar(select(StochasticEvent.id).where(
        StochasticEvent.run_id == run_id,
        StochasticEvent.provider_id == provider_id,
        StochasticEvent.event_type == "capacity_failure",
        StochasticEvent.start_time <= now,
        StochasticEvent.end_time > now,
    ).limit(1)) is not None


def _create_failure(db: Session, state, provider: Provider, now: datetime, severity: str, source: str) -> StochasticEvent:
    tag = (provider.name, now.strftime("%Y-%m-%dT%H:%M"), "failure", source)
    loss = float(choice(state.seed, LOSS_LEVELS, *tag, "loss"))
    if severity == "critical":
        loss = max(50.0, loss)
    duration = int(15 + uniform(state.seed, *tag, "duration") * 46)
    resource = choice(state.seed, ["CPU", "Both", "Both", "RAM"], *tag, "resource")
    name = "Provider Outage" if loss == 100 else choice(state.seed, FAILURE_NAMES[:-1], *tag, "name")
    event = StochasticEvent(
        run_id=state.current_run_id,
        provider_id=provider.id,
        event_type="capacity_failure",
        name=name,
        affected_resource=resource,
        start_time=now,
        end_time=now + timedelta(minutes=duration),
        magnitude_percent=0,
        capacity_loss_percent=loss,
        severity="critical" if loss >= 50 else severity,
        source=source,
        details={"duration_minutes": duration, "capacity_loss_percent": loss},
    )
    db.add(event)
    db.flush()
    record_event(
        db, "failure.started",
        f"{provider.name} {name}: {loss:.0f}% {resource} capacity unavailable for {duration} simulated minutes",
        severity="error" if loss >= 50 else "warning", provider_id=provider.id, simulation_time=now,
        details={"stochastic_event_id": event.id, "capacity_loss_percent": loss, "duration_minutes": duration, "resource": resource},
    )
    return event


def maybe_start_failure(db: Session, state, provider: Provider, now: datetime) -> StochasticEvent | None:
    if _active_failure(db, state.current_run_id, provider.id, now):
        return None
    profile_factor = 0.8 + personality(provider.name)["noise"] * 0.2
    probability = state.configuration["failures_per_hour"] * profile_factor / 60
    if uniform(state.seed, provider.name, now.strftime("%Y-%m-%dT%H:%M"), "failure-start") >= probability:
        return None
    critical = uniform(state.seed, provider.name, now.strftime("%Y-%m-%dT%H:%M"), "failure-severity") < 0.18
    return _create_failure(db, state, provider, now, "critical" if critical else "warning", "automatic")


def inject_failure(db: Session, state, provider: Provider, now: datetime, severity: str) -> StochasticEvent:
    return _create_failure(db, state, provider, now, severity, "manual")


def resolve_finished_failures(db: Session, state, now: datetime) -> None:
    events = db.scalars(select(StochasticEvent).where(
        StochasticEvent.run_id == state.current_run_id,
        StochasticEvent.active.is_(True),
        StochasticEvent.event_type == "capacity_failure",
        StochasticEvent.end_time <= now,
    )).all()
    for event in events:
        event.active = False
        record_event(
            db, "failure.recovered", f"{event.provider.name} recovered from {event.name}; full capacity restored",
            provider_id=event.provider_id, simulation_time=event.end_time,
            details={"stochastic_event_id": event.id, "capacity_loss_percent": event.capacity_loss_percent},
        )

