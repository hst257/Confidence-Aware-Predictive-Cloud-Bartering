from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (
    Provider,
    ResourceState,
    SimulationState,
)
from ..config import get_settings
from ..forecasting.model_manager import AVAILABLE_MODELS
from ..simulation.workload_generator import DEMO_PROVIDERS, seed_provider_workloads
from ..simulation.clock import simulation_epoch
from ..simulation.random_manager import random_seed
from ..simulation.run_service import create_run, finalize_run
from ..simulation.scenario_presets import DEFAULT_SCENARIO, DEFAULT_SEED, scenario_configuration
from ..simulation.stochastic_workload import workload_sample
from .event_service import record_event


def reset_demo(
    db: Session,
    *,
    seed: int | None = None,
    scenario: str | None = None,
    random_mode: bool | None = None,
    generate_new_seed: bool = False,
    forecast_model: str | None = None,
    shadow_models: list[str] | None = None,
    training_window_minutes: int | None = None,
    bartering_strategy: str | None = None,
    safety_margin_multiplier: float | None = None,
    model_selection_period_minutes: int | None = None,
) -> None:
    settings = get_settings()
    previous = db.get(SimulationState, 1)
    if previous and previous.current_run_id:
        finalize_run(db, previous)
    selected_scenario = scenario or (previous.scenario if previous else DEFAULT_SCENARIO)
    selected_random_mode = random_mode if random_mode is not None else (previous.random_mode if previous else False)
    selected_seed = random_seed() if generate_new_seed else (seed if seed is not None else (previous.seed if previous else DEFAULT_SEED))

    providers = db.scalars(select(Provider).order_by(Provider.id)).all()
    if not providers:
        providers = seed_provider_workloads(db)
    provider_defaults = {item["name"]: item for item in DEMO_PROVIDERS}
    for provider in providers:
        defaults = provider_defaults[provider.name]
        provider.total_cpu = defaults["total_cpu"]
        provider.total_ram = defaults["total_ram"]
        provider.credit_balance = defaults["credit_balance"]
        provider.sla_reputation = defaults["sla_reputation"]
        provider.forecast_reliability = defaults["forecast_reliability"]
        provider.contribution_score = defaults["contribution_score"]
        provider.successful_contracts = 0
        provider.failed_predictions = 0

    selected_model = forecast_model or (previous.forecast_model if previous else settings.default_forecast_model)
    selected_shadows = shadow_models if shadow_models is not None else (
        previous.shadow_models
        if previous is not None and previous.shadow_models is not None
        else AVAILABLE_MODELS
    )
    selected_window = training_window_minutes or (previous.training_window_minutes if previous else settings.default_training_window_minutes)
    selected_strategy = bartering_strategy or (previous.bartering_strategy if previous else "Confidence-Aware Predictive")
    selected_margin = safety_margin_multiplier if safety_margin_multiplier is not None else (previous.safety_margin_multiplier if previous else settings.safety_margin_multiplier)
    selected_period = model_selection_period_minutes or (previous.model_selection_period_minutes if previous else settings.model_selection_period_minutes)
    run = create_run(
        db, seed=selected_seed, scenario=selected_scenario, random_mode=selected_random_mode,
        forecast_model=selected_model, shadow_models=selected_shadows,
        training_window_minutes=selected_window, bartering_strategy=selected_strategy,
        safety_margin_multiplier=selected_margin, model_selection_period_minutes=selected_period,
    )
    state = previous or SimulationState(id=1, current_time=simulation_epoch())
    state.current_run_id = run.id
    state.current_time = simulation_epoch()
    state.running = False
    state.speed = 25
    state.seed = selected_seed
    state.scenario = selected_scenario
    state.random_mode = selected_random_mode
    state.configuration = scenario_configuration(selected_scenario)
    state.forecast_model = selected_model
    state.shadow_models = selected_shadows
    state.training_window_minutes = selected_window
    state.bartering_strategy = selected_strategy
    state.safety_margin_multiplier = selected_margin
    state.model_selection_period_minutes = selected_period
    state.model_assignments = {}
    state.last_model_selection_at = None
    state.last_real_tick = None
    state.last_sample_at = simulation_epoch()
    state.last_prediction_at = None
    state.started_at = datetime.utcnow()
    state.updated_at = datetime.utcnow()
    if previous is None:
        db.add(state)
    db.flush()
    for provider in providers:
        sample = workload_sample(db, state, provider, simulation_epoch())
        db.add(ResourceState(
            run_id=run.id, provider_id=provider.id, cpu_usage=sample.cpu, ram_usage=sample.ram,
            baseline_cpu=sample.baseline_cpu, baseline_ram=sample.baseline_ram,
            usable_cpu=sample.usable_cpu, usable_ram=sample.usable_ram,
            cpu_capacity_lost=sample.cpu_capacity_lost, ram_capacity_lost=sample.ram_capacity_lost,
            random_noise_cpu=sample.random_noise_cpu, random_noise_ram=sample.random_noise_ram,
            volatility=sample.volatility,
            cpu_available=max(0, sample.usable_cpu - sample.cpu), ram_available=max(0, sample.usable_ram - sample.ram),
            effective_future_cpu=max(0, sample.usable_cpu - sample.cpu), effective_future_ram=max(0, sample.usable_ram - sample.ram),
            simulation_time=simulation_epoch(), observed_at=datetime.utcnow(), source="seeded stochastic profile",
        ))
    record_event(
        db,
        "simulation.reset",
        f"Simulation run #{run.id} ready: {selected_scenario} scenario, seed {selected_seed}",
        simulation_time=simulation_epoch(),
        details={"run_id": run.id, "seed": selected_seed, "scenario": selected_scenario, "forecast_model": selected_model, "strategy": selected_strategy},
    )
    db.commit()


def seed_if_empty(db: Session) -> None:
    if not db.scalar(select(func.count(Provider.id))):
        reset_demo(db)
    elif not (db.get(SimulationState, 1) and db.get(SimulationState, 1).current_run_id):
        reset_demo(db)
