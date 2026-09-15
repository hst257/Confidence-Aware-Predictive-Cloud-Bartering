"""Correlated stochastic workload sampling over deterministic baselines."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Provider, ResourceState, StochasticEvent
from .random_manager import normal
from .workload_profiles import personality, workload_at


@dataclass(frozen=True)
class StochasticSample:
    baseline_cpu: float
    baseline_ram: float
    cpu: float
    ram: float
    usable_cpu: float
    usable_ram: float
    cpu_capacity_lost: float
    ram_capacity_lost: float
    random_noise_cpu: float
    random_noise_ram: float
    volatility: float
    active_event_ids: list[int]


def recent_volatility(db: Session, provider: Provider, run_id: int, now: datetime, minutes: int = 30) -> float:
    items = db.scalars(select(ResourceState).where(
        ResourceState.run_id == run_id,
        ResourceState.provider_id == provider.id,
        ResourceState.simulation_time >= now - timedelta(minutes=minutes),
        ResourceState.simulation_time < now,
    ).order_by(ResourceState.simulation_time.desc()).limit(minutes)).all()[::-1]
    if len(items) < 2:
        return round(personality(provider.name)["noise"] * 1.5, 2)
    changes = []
    for before, after in zip(items, items[1:]):
        cpu_change = abs(after.cpu_usage - before.cpu_usage) / max(provider.total_cpu, 1) * 100
        ram_change = abs(after.ram_usage - before.ram_usage) / max(provider.total_ram, 1) * 100
        changes.append((cpu_change + ram_change) / 2)
    return round(sum(changes) / len(changes), 2)


def workload_sample(db: Session, state, provider: Provider, now: datetime) -> StochasticSample:
    baseline = workload_at(provider.name, now)
    profile = personality(provider.name)
    previous = db.scalar(select(ResourceState).where(
        ResourceState.run_id == state.current_run_id,
        ResourceState.provider_id == provider.id,
        ResourceState.simulation_time < now,
    ).order_by(ResourceState.simulation_time.desc(), ResourceState.id.desc()))
    minute = now.strftime("%Y-%m-%dT%H:%M")
    cpu_target = normal(state.seed, provider.name, minute, "cpu-noise") * provider.total_cpu * 0.045 * profile["noise"] * state.configuration["noise_multiplier"]
    ram_target = normal(state.seed, provider.name, minute, "ram-noise") * provider.total_ram * 0.032 * profile["noise"] * state.configuration["noise_multiplier"]
    prior_cpu_noise = previous.random_noise_cpu if previous else 0
    prior_ram_noise = previous.random_noise_ram if previous else 0
    cpu_noise = prior_cpu_noise * 0.84 + cpu_target * 0.16
    ram_noise = prior_ram_noise * 0.86 + ram_target * 0.14

    events = db.scalars(select(StochasticEvent).where(
        StochasticEvent.run_id == state.current_run_id,
        StochasticEvent.provider_id == provider.id,
        StochasticEvent.start_time <= now,
        StochasticEvent.end_time > now,
    ).order_by(StochasticEvent.id)).all()
    cpu_effect = ram_effect = 0.0
    cpu_loss_percent = ram_loss_percent = 0.0
    for event in events:
        if event.event_type in {"workload_spike", "workload_drop"}:
            direction = 1 if event.event_type == "workload_spike" else -1
            if event.affected_resource in {"CPU", "Both"}:
                cpu_effect += direction * provider.total_cpu * event.magnitude_percent / 100
            if event.affected_resource in {"RAM", "Both"}:
                ram_effect += direction * provider.total_ram * event.magnitude_percent / 100
        elif event.event_type == "capacity_failure":
            if event.affected_resource in {"CPU", "Both"}:
                cpu_loss_percent += event.capacity_loss_percent
            if event.affected_resource in {"RAM", "Both"}:
                ram_loss_percent += event.capacity_loss_percent
    cpu_loss_percent = min(100, cpu_loss_percent)
    ram_loss_percent = min(100, ram_loss_percent)
    usable_cpu = provider.total_cpu * (1 - cpu_loss_percent / 100)
    usable_ram = provider.total_ram * (1 - ram_loss_percent / 100)
    cpu = max(0, min(provider.total_cpu * 1.65, baseline.cpu + cpu_noise + cpu_effect))
    ram = max(0, min(provider.total_ram * 1.65, baseline.ram + ram_noise + ram_effect))
    volatility = recent_volatility(db, provider, state.current_run_id, now)
    if previous:
        instant = (abs(cpu - previous.cpu_usage) / max(provider.total_cpu, 1) * 100 + abs(ram - previous.ram_usage) / max(provider.total_ram, 1) * 100) / 2
        volatility = round(volatility * 0.8 + instant * 0.2, 2)
    return StochasticSample(
        baseline_cpu=round(baseline.cpu, 2), baseline_ram=round(baseline.ram, 2),
        cpu=round(cpu, 2), ram=round(ram, 2), usable_cpu=round(usable_cpu, 2), usable_ram=round(usable_ram, 2),
        cpu_capacity_lost=round(provider.total_cpu - usable_cpu, 2), ram_capacity_lost=round(provider.total_ram - usable_ram, 2),
        random_noise_cpu=round(cpu_noise, 3), random_noise_ram=round(ram_noise, 3), volatility=volatility,
        active_event_ids=[event.id for event in events],
    )

