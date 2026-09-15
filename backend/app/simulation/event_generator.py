"""Seeded workload-event generation, separate from marketplace decisions."""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Provider, StochasticEvent
from ..services.event_service import record_event
from .random_manager import choice, uniform
from .workload_profiles import personality

SPIKE_NAMES = ["Flash Crowd", "API Burst", "Batch Job", "Video Processing Burst", "Customer Campaign", "Unexpected Traffic Surge"]
DROP_NAMES = ["Batch Job Completed", "Customer Traffic Ended", "Service Scaled Down"]


def _minute_key(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M")


def _has_active(db: Session, run_id: int, provider_id: int, event_type: str, now: datetime) -> bool:
    return db.scalar(select(StochasticEvent.id).where(
        StochasticEvent.run_id == run_id,
        StochasticEvent.provider_id == provider_id,
        StochasticEvent.event_type == event_type,
        StochasticEvent.start_time <= now,
        StochasticEvent.end_time > now,
    ).limit(1)) is not None


def _create_workload_event(
    db: Session,
    *,
    run_id: int,
    provider: Provider,
    now: datetime,
    event_type: str,
    severity: str,
    seed: int,
    configuration: dict,
    source: str = "automatic",
) -> StochasticEvent:
    profile = personality(provider.name)
    tag = (provider.name, _minute_key(now), event_type, source)
    is_spike = event_type == "workload_spike"
    names = profile["preferred_spikes"] if is_spike else DROP_NAMES
    name = choice(seed, names, *tag, "name")
    duration = int(8 + uniform(seed, *tag, "duration") * (24 if is_spike else 18))
    magnitude_base = 14 + uniform(seed, *tag, "magnitude") * (25 if is_spike else 18)
    magnitude = magnitude_base * configuration["magnitude_multiplier"] * (profile["spike_magnitude"] if is_spike else 0.8)
    if severity == "critical":
        magnitude *= 1.45
        duration += 8
    affected = choice(seed, ["CPU", "CPU", "RAM", "Both"], *tag, "resource")
    event = StochasticEvent(
        run_id=run_id,
        provider_id=provider.id,
        event_type=event_type,
        name=name,
        affected_resource=affected,
        start_time=now,
        end_time=now + timedelta(minutes=duration),
        magnitude_percent=round(magnitude, 2),
        severity=severity,
        source=source,
        details={"duration_minutes": duration, "direction": "increase" if is_spike else "decrease"},
    )
    db.add(event)
    db.flush()
    direction = "+" if is_spike else "−"
    record_event(
        db,
        f"workload.{event_type.removeprefix('workload_')}_started",
        f"{provider.name} {name} started: {affected} {direction}{magnitude:.0f}% for {duration} simulated minutes",
        severity="error" if severity == "critical" else "warning",
        provider_id=provider.id,
        simulation_time=now,
        details={"stochastic_event_id": event.id, "magnitude_percent": round(magnitude, 2), "duration_minutes": duration, "resource": affected},
    )
    return event


def maybe_start_workload_events(db: Session, state, provider: Provider, now: datetime) -> list[StochasticEvent]:
    run_id = state.current_run_id
    seed = state.seed
    config = state.configuration
    profile = personality(provider.name)
    key = (provider.name, _minute_key(now))
    created: list[StochasticEvent] = []
    spike_probability = config["spikes_per_hour"] * profile["spike_rate"] / 60
    drop_probability = config["drops_per_hour"] * profile["drop_rate"] / 60
    if not _has_active(db, run_id, provider.id, "workload_spike", now) and uniform(seed, *key, "spike-start") < spike_probability:
        rare = uniform(seed, *key, "abnormal") < 0.035
        created.append(_create_workload_event(
            db, run_id=run_id, provider=provider, now=now, event_type="workload_spike",
            severity="critical" if rare else "warning", seed=seed, configuration=config,
        ))
    if not _has_active(db, run_id, provider.id, "workload_drop", now) and uniform(seed, *key, "drop-start") < drop_probability:
        created.append(_create_workload_event(
            db, run_id=run_id, provider=provider, now=now, event_type="workload_drop",
            severity="info", seed=seed, configuration=config,
        ))
    return created


def inject_workload_event(db: Session, state, provider: Provider, now: datetime, kind: str, severity: str) -> StochasticEvent:
    event_type = "workload_spike" if kind == "spike" else "workload_drop"
    return _create_workload_event(
        db, run_id=state.current_run_id, provider=provider, now=now, event_type=event_type,
        severity=severity, seed=state.seed, configuration=state.configuration, source="manual",
    )


def resolve_finished_workload_events(db: Session, state, now: datetime) -> None:
    events = db.scalars(select(StochasticEvent).where(
        StochasticEvent.run_id == state.current_run_id,
        StochasticEvent.active.is_(True),
        StochasticEvent.event_type.in_(["workload_spike", "workload_drop"]),
        StochasticEvent.end_time <= now,
    )).all()
    for event in events:
        event.active = False
        record_event(
            db, "workload.event_ended", f"{event.provider.name} {event.name} ended; workload returned toward baseline",
            provider_id=event.provider_id, simulation_time=event.end_time,
            details={"stochastic_event_id": event.id},
        )

