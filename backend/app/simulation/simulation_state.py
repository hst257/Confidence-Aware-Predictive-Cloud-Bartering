from datetime import datetime

from sqlalchemy.orm import Session

from ..config import get_settings
from ..forecasting.model_manager import AVAILABLE_MODELS
from ..models import SimulationState
from .clock import display_time, simulation_epoch
from .run_service import create_run
from .scenario_presets import DEFAULT_SCENARIO, DEFAULT_SEED, SCENARIO_PRESETS, scenario_configuration


ALLOWED_SPEEDS = (1, 2, 5, 10, 25, 50, 100)


def get_or_create_state(db: Session) -> SimulationState:
    settings = get_settings()
    state = db.get(SimulationState, 1)
    if state is None:
        run = create_run(db, seed=DEFAULT_SEED, scenario=DEFAULT_SCENARIO)
        state = SimulationState(
            id=1,
            current_run_id=run.id,
            current_time=simulation_epoch(),
            running=False,
            speed=25,
            seed=DEFAULT_SEED,
            scenario=DEFAULT_SCENARIO,
            configuration=scenario_configuration(DEFAULT_SCENARIO),
            forecast_model=settings.default_forecast_model,
            shadow_models=AVAILABLE_MODELS,
            training_window_minutes=settings.default_training_window_minutes,
            bartering_strategy="Confidence-Aware Predictive",
            safety_margin_multiplier=settings.safety_margin_multiplier,
            model_selection_period_minutes=settings.model_selection_period_minutes,
            model_assignments={},
            last_sample_at=simulation_epoch(),
        )
        db.add(state)
        db.flush()
    elif state.current_run_id is None:
        scenario = state.scenario or DEFAULT_SCENARIO
        seed = state.seed or DEFAULT_SEED
        run = create_run(db, seed=seed, scenario=scenario, random_mode=bool(state.random_mode))
        state.current_run_id = run.id
        state.configuration = scenario_configuration(scenario)
        db.flush()
    return state


def state_payload(state: SimulationState) -> dict:
    day, clock = display_time(state.current_time)
    return {
        "id": state.id,
        "current_time": state.current_time,
        "day": day,
        "clock": clock,
        "running": state.running,
        "status": "Running" if state.running else "Paused",
        "speed": state.speed,
        "run_id": state.current_run_id,
        "seed": state.seed,
        "scenario": state.scenario,
        "mode": "Random" if state.random_mode else "Reproducible",
        "random_mode": state.random_mode,
        "configuration": state.configuration or {},
        "forecast_model": state.forecast_model,
        "shadow_models": state.shadow_models or [],
        "training_window_minutes": state.training_window_minutes,
        "bartering_strategy": state.bartering_strategy,
        "safety_margin_multiplier": state.safety_margin_multiplier,
        "model_selection_period_minutes": state.model_selection_period_minutes,
        "model_assignments": state.model_assignments or {},
        "available_models": ["Auto", *AVAILABLE_MODELS],
        "available_training_windows": [120, 360, 720, 1440, 4320],
        "available_strategies": ["Reactive Only", "Predictive", "Confidence-Aware Predictive"],
        "available_scenarios": list(SCENARIO_PRESETS),
        "allowed_speeds": list(ALLOWED_SPEEDS),
        "last_sample_at": state.last_sample_at,
        "last_prediction_at": state.last_prediction_at,
    }


def pause_state(state: SimulationState) -> None:
    state.running = False
    state.last_real_tick = None
    state.updated_at = datetime.utcnow()
