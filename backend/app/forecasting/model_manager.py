from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Prediction, PredictionEvaluation, PredictionKind, Provider, ResourceState, SimulationState
from ..services.event_service import record_event
from .base_model import ForecastModel, Observation
from .confidence import CONFIDENCE_FORMULA, confidence_from_uncertainty
from .linear_trend import LinearTrendForecastModel
from .moving_average import MovingAverageForecastModel
from .naive_model import NaiveForecastModel
from .statistical_model import HoltWintersForecastModel


MODEL_TYPES: dict[str, type[ForecastModel]] = {
    "Naive": NaiveForecastModel,
    "Moving Average": MovingAverageForecastModel,
    "Linear Trend": LinearTrendForecastModel,
    "Holt-Winters": HoltWintersForecastModel,
}
AVAILABLE_MODELS = list(MODEL_TYPES)


def _history(db: Session, state: SimulationState, provider: Provider, generated_at: datetime) -> list[Observation]:
    # This <= predicate is the hard prediction/truth boundary for every model.
    rows = db.scalars(select(ResourceState).where(
        ResourceState.run_id == state.current_run_id,
        ResourceState.provider_id == provider.id,
        ResourceState.simulation_time >= generated_at - timedelta(minutes=state.training_window_minutes),
        ResourceState.simulation_time <= generated_at,
    ).order_by(ResourceState.simulation_time, ResourceState.id)).all()
    return [Observation(item.simulation_time, item.cpu_usage, item.ram_usage) for item in rows]


def _best_model(db: Session, state: SimulationState, provider: Provider, generated_at: datetime) -> str:
    assignments = dict(state.model_assignments or {})
    due = state.last_model_selection_at is None or generated_at - state.last_model_selection_at >= timedelta(minutes=state.model_selection_period_minutes)
    if not due and provider.name in assignments:
        return assignments[provider.name]
    scores: list[tuple[float, str]] = []
    for name in AVAILABLE_MODELS:
        rows = db.scalars(select(PredictionEvaluation).where(
            PredictionEvaluation.run_id == state.current_run_id,
            PredictionEvaluation.provider_id == provider.id,
            PredictionEvaluation.model_name == name,
        ).order_by(PredictionEvaluation.simulation_time.desc()).limit(40)).all()
        if len(rows) >= 3:
            scores.append((sum(item.percentage_error for item in rows) / len(rows), name))
    selected = min(scores)[1] if scores else assignments.get(provider.name, "Naive")
    assignments[provider.name] = selected
    state.model_assignments = assignments
    return selected


def _trained_model(requested: str, history: list[Observation]) -> tuple[ForecastModel, str | None]:
    requested_type = MODEL_TYPES[requested]
    if len(history) >= requested_type.minimum_points:
        return requested_type().train(history), None
    fallback_type: type[ForecastModel] = MovingAverageForecastModel if len(history) >= MovingAverageForecastModel.minimum_points else NaiveForecastModel
    return fallback_type().train(history), fallback_type.name


def _safe_capacity(strategy: str, free: float, uncertainty: float, multiplier: float) -> float:
    if strategy == "Reactive Only":
        return 0.0
    if strategy == "Predictive":
        return max(0.0, free)
    return max(0.0, free - uncertainty * multiplier)


def generate_forecasts(db: Session, generated_at: datetime) -> list[Prediction]:
    settings = get_settings()
    state = db.get(SimulationState, 1)
    if state is None or state.current_run_id is None:
        return []
    configured_model = state.forecast_model if state.forecast_model in {"Auto", *AVAILABLE_MODELS} else "Auto"
    if configured_model != state.forecast_model:
        state.forecast_model = configured_model
        record_event(
            db, "prediction.configuration_repaired",
            "Unknown forecast model was replaced with Auto",
            severity="warning", simulation_time=generated_at,
        )
    providers = db.scalars(select(Provider).order_by(Provider.id)).all()
    histories = {provider.id: _history(db, state, provider, generated_at) for provider in providers}
    usable_provider_ids = {provider_id for provider_id, history in histories.items() if history}
    if not usable_provider_ids:
        record_event(
            db, "prediction.cycle_skipped",
            "Forecasting cycle skipped because this run has no observations yet",
            severity="warning", simulation_time=generated_at,
            details={"run_id": state.current_run_id, "strict_history_cutoff": generated_at.isoformat()},
        )
        return []
    for active in db.scalars(select(Prediction).where(
        Prediction.run_id == state.current_run_id,
        Prediction.provider_id.in_(usable_provider_ids),
        Prediction.superseded.is_(False),
    )).all():
        active.superseded = True
    recent_evaluations: dict[tuple[int, str, int], list[PredictionEvaluation]] = {}
    for item in db.scalars(select(PredictionEvaluation).where(
        PredictionEvaluation.run_id == state.current_run_id,
    ).order_by(PredictionEvaluation.simulation_time.desc())).all():
        key = (item.provider_id, item.model_name, item.horizon_minutes)
        bucket = recent_evaluations.setdefault(key, [])
        if len(bucket) < 20:
            bucket.append(item)
    revision_map = {
        (provider_id, model_name, window_start): revision
        for provider_id, model_name, window_start, revision in db.execute(select(
            Prediction.provider_id, Prediction.model_name, Prediction.window_start,
            func.max(Prediction.revision_number),
        ).where(Prediction.run_id == state.current_run_id).group_by(
            Prediction.provider_id, Prediction.model_name, Prediction.window_start,
        )).all()
    }
    cycle_id = f"R{state.current_run_id}-" + generated_at.strftime("D%j-%H%M")
    generated: list[Prediction] = []
    record_event(db, "prediction.cycle_started", f"Historical forecasting cycle started for {len(settings.prediction_horizons)} horizons", simulation_time=generated_at, details={"cycle_id": cycle_id, "strict_history_cutoff": generated_at.isoformat()})
    for provider in providers:
        history = histories[provider.id]
        if not history:
            record_event(
                db, "prediction.provider_skipped",
                f"{provider.name} forecast skipped because no observations were available",
                severity="warning", provider_id=provider.id, simulation_time=generated_at,
                details={"run_id": state.current_run_id, "strict_history_cutoff": generated_at.isoformat()},
            )
            continue
        decision_model = _best_model(db, state, provider, generated_at) if configured_model == "Auto" else configured_model
        requested_models = list(dict.fromkeys([decision_model, *(state.shadow_models or [])]))
        if configured_model == "Auto":
            requested_models = list(dict.fromkeys([*requested_models, *AVAILABLE_MODELS]))
        for requested_model in requested_models:
            if requested_model not in MODEL_TYPES:
                continue
            model, fallback = _trained_model(requested_model, history)
            if fallback:
                record_event(db, "prediction.model_fallback", f"{provider.name} {requested_model} used {fallback}: only {len(history)} training samples", severity="warning", provider_id=provider.id, simulation_time=generated_at, details={"requested_model": requested_model, "fallback_model": fallback, "training_points": len(history)})
            for horizon in settings.prediction_horizons:
                result = model.predict(horizon)
                target = generated_at + timedelta(minutes=horizon)
                predicted_cpu = round(max(0, min(provider.total_cpu * 1.65, result.cpu)), 2)
                predicted_ram = round(max(0, min(provider.total_ram * 1.65, result.ram)), 2)
                uncertainty_cpu = round(max(0.5, result.uncertainty_cpu), 2)
                uncertainty_ram = round(max(0.75, result.uncertainty_ram), 2)
                latest = history[-1]
                current_resource = db.scalar(select(ResourceState).where(
                    ResourceState.run_id == state.current_run_id,
                    ResourceState.provider_id == provider.id,
                    ResourceState.simulation_time <= generated_at,
                ).order_by(ResourceState.simulation_time.desc(), ResourceState.id.desc()))
                usable_cpu = current_resource.usable_cpu if current_resource else provider.total_cpu
                usable_ram = current_resource.usable_ram if current_resource else provider.total_ram
                free_cpu, free_ram = max(0, usable_cpu - predicted_cpu), max(0, usable_ram - predicted_ram)
                volatility = current_resource.volatility if current_resource else 0
                recent_items = recent_evaluations.get((provider.id, requested_model, horizon), [])
                weights = [0.9 ** index for index in range(len(recent_items))]
                recent_error = (
                    sum(item.percentage_error * weight for item, weight in zip(recent_items, weights)) / sum(weights)
                    if recent_items else 12.0
                )
                confidence = confidence_from_uncertainty(
                    uncertainty_cpu=uncertainty_cpu, uncertainty_ram=uncertainty_ram,
                    total_cpu=provider.total_cpu, total_ram=provider.total_ram,
                    recent_error=recent_error,
                    volatility=volatility, horizon_minutes=horizon, insufficient_history=fallback is not None,
                )
                revision_key = (provider.id, requested_model, target)
                revision = (revision_map.get(revision_key) or 0) + 1
                revision_map[revision_key] = revision
                decision = requested_model == decision_model
                prediction = Prediction(
                    run_id=state.current_run_id, provider_id=provider.id,
                    predicted_cpu_usage=predicted_cpu, predicted_ram_usage=predicted_ram,
                    predicted_cpu_spare=round(free_cpu, 2), predicted_ram_spare=round(free_ram, 2),
                    cpu_deficit=round(max(0, predicted_cpu - usable_cpu), 2), ram_deficit=round(max(0, predicted_ram - usable_ram), 2),
                    safe_cpu_commitment=round(_safe_capacity(state.bartering_strategy, free_cpu, uncertainty_cpu, state.safety_margin_multiplier), 2),
                    safe_ram_commitment=round(_safe_capacity(state.bartering_strategy, free_ram, uncertainty_ram, state.safety_margin_multiplier), 2),
                    confidence=confidence, window_start=target, window_end=target + timedelta(minutes=settings.contract_duration_minutes),
                    simulation_generated_at=generated_at, horizon_minutes=horizon, cycle_id=cycle_id,
                    recent_volatility=volatility, kind=PredictionKind.REVISED if revision > 1 else PredictionKind.INITIAL,
                    model_name=requested_model, decision_forecast=decision, uncertainty_cpu=uncertainty_cpu, uncertainty_ram=uncertainty_ram,
                    fallback_model=fallback, training_points=len(history), training_window_minutes=state.training_window_minutes,
                    revision_number=revision, model_metadata={**result.metadata, "history_cutoff": generated_at.isoformat(), "last_observation": latest.timestamp.isoformat(), "confidence_formula": CONFIDENCE_FORMULA, "effective_model": fallback or requested_model},
                )
                db.add(prediction)
                db.flush()
                generated.append(prediction)
                if decision and horizon == settings.planning_horizon_minutes:
                    deficit = prediction.cpu_deficit > 0 or prediction.ram_deficit > 0
                    record_event(
                        db, "prediction.deficit" if deficit else "prediction.surplus",
                        f"{provider.name} {requested_model} forecast {'deficit' if deficit else 'surplus'} for {target:%H:%M}: {confidence:g}% confidence, ±{uncertainty_cpu:g} CPU",
                        severity="warning" if deficit else "info", provider_id=provider.id, simulation_time=generated_at,
                        details={"prediction_id": prediction.id, "model": requested_model, "uncertainty_cpu": uncertainty_cpu, "uncertainty_ram": uncertainty_ram, "history_cutoff": generated_at.isoformat(), "future_events_hidden": True},
                    )
    if configured_model == "Auto":
        state.last_model_selection_at = generated_at
        record_event(db, "prediction.auto_models_selected", "Auto model assignments refreshed", simulation_time=generated_at, details={"assignments": state.model_assignments})
    return generated
