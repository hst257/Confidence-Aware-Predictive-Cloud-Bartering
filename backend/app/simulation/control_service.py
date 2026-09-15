from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..services.demo_service import reset_demo
from ..services.event_service import record_event
from .engine import _advance_running_clock, advance_to
from .mutation_lock import simulation_mutation
from .random_manager import random_seed
from .run_service import finalize_run, update_run_progress
from .scenario_presets import SCENARIO_PRESETS
from .simulation_state import ALLOWED_SPEEDS, get_or_create_state, pause_state


def start(db: Session):
    with simulation_mutation(db):
        state = get_or_create_state(db)
        if not state.running:
            state.running = True
            state.last_real_tick = datetime.utcnow()
            record_event(db, "simulation.started", f"Simulation started at {state.speed}×", simulation_time=state.current_time)
            update_run_progress(db, state, "Running")
            db.commit()
        return state


def pause(db: Session):
    with simulation_mutation(db):
        _advance_running_clock(db)
        state = get_or_create_state(db)
        if state.running:
            pause_state(state)
            record_event(db, "simulation.paused", "Simulation paused", simulation_time=state.current_time)
            finalize_run(db, state, "Paused")
            db.commit()
        return state


def set_speed(db: Session, speed: int):
    if speed not in ALLOWED_SPEEDS:
        raise HTTPException(status_code=422, detail=f"Speed must be one of {list(ALLOWED_SPEEDS)}")
    with simulation_mutation(db):
        _advance_running_clock(db)
        state = get_or_create_state(db)
        old_speed = state.speed
        state.speed = speed
        state.last_real_tick = datetime.utcnow() if state.running else None
        record_event(
            db,
            "simulation.speed_changed",
            f"Simulation speed changed from {old_speed}× to {speed}×",
            simulation_time=state.current_time,
            details={"old_speed": old_speed, "new_speed": speed},
        )
        db.commit()
        return state


def step_forward(db: Session, minutes: int):
    with simulation_mutation(db):
        state = get_or_create_state(db)
        target = state.current_time + timedelta(minutes=minutes)
        advance_to(db, target)
        state.last_real_tick = datetime.utcnow() if state.running else None
        record_event(
            db,
            "simulation.stepped",
            f"Simulation stepped forward {minutes} minutes",
            simulation_time=state.current_time,
            details={"minutes": minutes},
        )
        db.commit()
        return state


def reset(db: Session):
    with simulation_mutation(db):
        reset_demo(db)
        return get_or_create_state(db)


def configure(
    db: Session, *, scenario: str, seed: int | None, random_mode: bool,
):
    with simulation_mutation(db):
        state = get_or_create_state(db)
        if state.running:
            raise HTTPException(status_code=409, detail="Pause the simulation before changing its scenario or seed")
        if scenario not in SCENARIO_PRESETS:
            raise HTTPException(status_code=422, detail=f"Scenario must be one of {list(SCENARIO_PRESETS)}")
        selected_seed = random_seed() if seed is None else seed
        if selected_seed < 1 or selected_seed > 2_147_483_647:
            raise HTTPException(status_code=422, detail="Seed must be between 1 and 2147483647")
        reset_demo(db, seed=selected_seed, scenario=scenario, random_mode=random_mode)
        return get_or_create_state(db)


def restart_same_seed(db: Session):
    with simulation_mutation(db):
        state = get_or_create_state(db)
        if state.running:
            raise HTTPException(status_code=409, detail="Pause the simulation before restarting the run")
        reset_demo(db, seed=state.seed, scenario=state.scenario, random_mode=state.random_mode)
        return get_or_create_state(db)


def generate_seed_and_restart(db: Session):
    with simulation_mutation(db):
        state = get_or_create_state(db)
        if state.running:
            raise HTTPException(status_code=409, detail="Pause the simulation before generating a new seed")
        reset_demo(db, scenario=state.scenario, random_mode=True, generate_new_seed=True)
        return get_or_create_state(db)
