import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import SessionLocal
from ..models import (
    BarterContract,
    ContractStatus,
    Provider,
    ResourceState,
)
from ..forecasting.evaluator import evaluate_due_predictions
from ..services.automatic_marketplace_service import auto_match_and_create
from ..services.contract_service import complete_contract, fail_contract, transition_to_active
from ..services.emergency_matching_service import process_current_shortages, react_to_failed_commitments
from ..services.event_service import record_event
from ..services.renegotiation_service import monitor_contract_risk
from .clock import advance_time
from .event_generator import maybe_start_workload_events, resolve_finished_workload_events
from .failure_generator import maybe_start_failure, resolve_finished_failures
from .mutation_lock import simulation_mutation
from .prediction_generator import generate_simulation_predictions
from .run_service import update_run_progress
from .simulation_state import get_or_create_state
from .stochastic_workload import workload_sample

logger = logging.getLogger(__name__)
OPEN_RESERVATION_STATUSES = [
    ContractStatus.PROPOSED,
    ContractStatus.SCHEDULED,
    ContractStatus.AT_RISK,
    ContractStatus.ACTIVE,
]


def _future_reservations(db: Session, run_id: int, provider_id: int, simulation_time: datetime) -> tuple[float, float]:
    contracts = db.scalars(select(BarterContract).where(
        BarterContract.run_id == run_id,
        BarterContract.provider_id == provider_id,
        BarterContract.status.in_(OPEN_RESERVATION_STATUSES),
        BarterContract.end_time > simulation_time,
    )).all()
    return sum(item.cpu_amount for item in contracts), sum(item.ram_amount for item in contracts)


def sample_resources(db: Session, simulation_time: datetime) -> list[ResourceState]:
    state = get_or_create_state(db)
    resolve_finished_workload_events(db, state, simulation_time)
    resolve_finished_failures(db, state, simulation_time)
    states: list[ResourceState] = []
    for provider in db.scalars(select(Provider).order_by(Provider.id)).all():
        maybe_start_workload_events(db, state, provider, simulation_time)
        maybe_start_failure(db, state, provider, simulation_time)
        sample = workload_sample(db, state, provider, simulation_time)
        cpu_available = max(0, sample.usable_cpu - sample.cpu)
        ram_available = max(0, sample.usable_ram - sample.ram)
        reserved_cpu, reserved_ram = _future_reservations(db, state.current_run_id, provider.id, simulation_time)
        resource = ResourceState(
            run_id=state.current_run_id,
            provider_id=provider.id,
            cpu_usage=sample.cpu,
            ram_usage=sample.ram,
            baseline_cpu=sample.baseline_cpu,
            baseline_ram=sample.baseline_ram,
            usable_cpu=sample.usable_cpu,
            usable_ram=sample.usable_ram,
            cpu_capacity_lost=sample.cpu_capacity_lost,
            ram_capacity_lost=sample.ram_capacity_lost,
            random_noise_cpu=sample.random_noise_cpu,
            random_noise_ram=sample.random_noise_ram,
            volatility=sample.volatility,
            cpu_available=round(cpu_available, 2),
            ram_available=round(ram_available, 2),
            reserved_future_cpu=round(reserved_cpu, 2),
            reserved_future_ram=round(reserved_ram, 2),
            effective_future_cpu=round(max(0, cpu_available - reserved_cpu), 2),
            effective_future_ram=round(max(0, ram_available - reserved_ram), 2),
            simulation_time=simulation_time,
            observed_at=datetime.utcnow(),
            source="stochastic profile",
        )
        db.add(resource)
        states.append(resource)
    db.flush()
    return states


def process_contract_lifecycle(db: Session, simulation_time: datetime) -> None:
    state = get_or_create_state(db)
    unsafe = db.scalars(select(BarterContract).where(
        BarterContract.run_id == state.current_run_id,
        BarterContract.status == ContractStatus.AT_RISK,
        BarterContract.start_time <= simulation_time,
    ).order_by(BarterContract.id)).all()
    for contract in unsafe:
        fail_contract(db, contract, simulation_time=contract.start_time, commit=False)

    scheduled = db.scalars(select(BarterContract).where(
        BarterContract.run_id == state.current_run_id,
        BarterContract.status == ContractStatus.SCHEDULED,
        BarterContract.start_time <= simulation_time,
    ).order_by(BarterContract.id)).all()
    for contract in scheduled:
        transition_to_active(db, contract, simulation_time=contract.start_time, commit=False)

    active = db.scalars(select(BarterContract).where(
        BarterContract.run_id == state.current_run_id,
        BarterContract.status == ContractStatus.ACTIVE,
        BarterContract.end_time <= simulation_time,
    ).order_by(BarterContract.id)).all()
    for contract in active:
        actual = db.scalar(select(ResourceState).where(
            ResourceState.run_id == state.current_run_id,
            ResourceState.provider_id == contract.provider_id,
            ResourceState.simulation_time <= contract.end_time,
        ).order_by(ResourceState.simulation_time.desc(), ResourceState.id.desc()))
        actual_cpu_spare = actual.cpu_available if actual else 0
        actual_ram_spare = actual.ram_available if actual else 0
        if actual_cpu_spare + 0.01 >= contract.cpu_amount and actual_ram_spare + 0.01 >= contract.ram_amount:
            complete_contract(db, contract, actual_cpu_spare, actual_ram_spare, simulation_time=contract.end_time, commit=False)
        else:
            fail_contract(db, contract, simulation_time=contract.end_time, commit=False)


def _prediction_cycle(db: Session, when: datetime) -> None:
    forecasts = generate_simulation_predictions(db, when)
    state = get_or_create_state(db)
    state.last_prediction_at = when
    db.flush()
    monitor_contract_risk(db, when)
    db.flush()
    if forecasts:
        auto_match_and_create(db, forecasts[0].cycle_id, when)


def advance_to(db: Session, target_time: datetime) -> None:
    settings = get_settings()
    state = get_or_create_state(db)
    if target_time <= state.current_time:
        return
    next_sample = state.last_sample_at + timedelta(seconds=settings.resource_sample_seconds) if state.last_sample_at else state.current_time
    next_prediction = state.last_prediction_at + timedelta(minutes=settings.prediction_interval_minutes) if state.last_prediction_at else state.current_time.replace(second=0, microsecond=0)
    while min(next_sample, next_prediction) <= target_time:
        action_time = min(next_sample, next_prediction)
        if next_sample == action_time:
            sample_resources(db, action_time)
            state.last_sample_at = action_time
            db.flush()
            process_contract_lifecycle(db, action_time)
            react_to_failed_commitments(db, action_time)
            process_current_shortages(db, action_time)
            evaluate_due_predictions(db, action_time)
            next_sample += timedelta(seconds=settings.resource_sample_seconds)
        if next_prediction == action_time:
            _prediction_cycle(db, action_time)
            next_prediction += timedelta(minutes=settings.prediction_interval_minutes)
    process_contract_lifecycle(db, target_time)
    evaluate_due_predictions(db, target_time)
    state.current_time = target_time
    state.updated_at = datetime.utcnow()
    update_run_progress(db, state)


def _advance_running_clock(db: Session) -> None:
    state = get_or_create_state(db)
    if not state.running:
        return
    now = datetime.utcnow()
    if state.last_real_tick is None:
        state.last_real_tick = now
        return
    real_elapsed = min(3.0, max(0.0, (now - state.last_real_tick).total_seconds()))
    target = advance_time(state.current_time, real_elapsed, state.speed)
    state.last_real_tick = now
    advance_to(db, target)


def advance_running_clock(db: Session) -> None:
    """Advance and commit one clock tick as an atomic simulation mutation."""
    with simulation_mutation(db):
        _advance_running_clock(db)
        db.commit()


async def run_engine_loop() -> None:
    settings = get_settings()
    while True:
        await asyncio.sleep(settings.simulation_tick_real_seconds)
        try:
            with SessionLocal() as db:
                advance_running_clock(db)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Simulation tick failed")
