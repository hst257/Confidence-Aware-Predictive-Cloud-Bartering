"""Simulation-run lifecycle and persisted reproducibility metadata."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import SimulationRun, SimulationState
from .clock import simulation_epoch
from .scenario_presets import DEFAULT_SCENARIO, DEFAULT_SEED, scenario_configuration


def current_run(db: Session) -> SimulationRun | None:
    state = db.get(SimulationState, 1)
    return db.get(SimulationRun, state.current_run_id) if state and state.current_run_id else None


def create_run(
    db: Session, *, seed: int = DEFAULT_SEED, scenario: str = DEFAULT_SCENARIO,
    random_mode: bool = False,
) -> SimulationRun:
    configuration = scenario_configuration(scenario)
    run = SimulationRun(
        seed=seed,
        scenario=scenario,
        random_mode=random_mode,
        status="Ready",
        starting_time=simulation_epoch(),
        configuration=configuration,
        final_statistics={},
    )
    db.add(run)
    db.flush()
    return run


def update_run_progress(db: Session, state: SimulationState, status: str | None = None) -> SimulationRun | None:
    run = db.get(SimulationRun, state.current_run_id) if state.current_run_id else None
    if not run:
        return None
    run.ending_time = state.current_time
    run.simulation_duration_minutes = round((state.current_time - run.starting_time).total_seconds() / 60, 2)
    run.status = status or ("Running" if state.running else "Paused")
    run.updated_at = datetime.utcnow()
    return run


def finalize_run(db: Session, state: SimulationState, status: str = "Completed") -> SimulationRun | None:
    run = update_run_progress(db, state, status)
    if run:
        from ..services.analytics_service import analytics_summary

        run.final_statistics = analytics_summary(db, run_id=run.id, include_runs=False)
    return run


def list_run_summaries(db: Session, limit: int = 20) -> list[dict]:
    runs = db.scalars(select(SimulationRun).order_by(SimulationRun.id.desc()).limit(limit)).all()
    return [
        {
            "id": run.id,
            "seed": run.seed,
            "scenario": run.scenario,
            "random_mode": run.random_mode,
            "status": run.status,
            "starting_time": run.starting_time,
            "ending_time": run.ending_time,
            "simulation_duration_minutes": run.simulation_duration_minutes,
            "configuration": run.configuration,
            "final_statistics": run.final_statistics,
        }
        for run in runs
    ]
