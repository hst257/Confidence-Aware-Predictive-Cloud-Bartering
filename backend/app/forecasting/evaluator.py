from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Prediction, PredictionEvaluation, Provider, ReputationHistory, ResourceState, SimulationState, StochasticEvent
from ..services.event_service import record_event


def _attribution(db: Session, prediction: Prediction, actual: ResourceState, percentage_error: float) -> str:
    event = db.scalar(select(StochasticEvent).where(
        StochasticEvent.run_id == prediction.run_id, StochasticEvent.provider_id == prediction.provider_id,
        StochasticEvent.start_time <= prediction.window_start, StochasticEvent.end_time > prediction.window_start,
    ).order_by(StochasticEvent.capacity_loss_percent.desc(), StochasticEvent.magnitude_percent.desc()))
    if event:
        if event.event_type == "capacity_failure":
            return "Provider failure"
        return "Traffic spike" if event.event_type == "workload_spike" else "Workload drop"
    if prediction.fallback_model:
        return "Insufficient training history"
    if prediction.recent_volatility >= 4:
        return "High workload volatility"
    before = db.scalar(select(ResourceState).where(
        ResourceState.run_id == prediction.run_id, ResourceState.provider_id == prediction.provider_id,
        ResourceState.simulation_time <= prediction.window_start - timedelta(minutes=15),
    ).order_by(ResourceState.simulation_time.desc(), ResourceState.id.desc()))
    if before:
        actual_change = actual.cpu_usage - before.cpu_usage
        predicted_trend = float((prediction.model_metadata or {}).get("cpu_trend", 0))
        if abs(actual_change) > 3 and actual_change * predicted_trend < 0:
            return "Trend reversal"
    return "Model mismatch" if percentage_error >= 20 else "Normal forecast error"


def _update_reliability(db: Session, state: SimulationState, provider_id: int, now: datetime) -> None:
    provider = db.get(Provider, provider_id)
    rows = db.execute(select(PredictionEvaluation, Prediction).join(
        Prediction, Prediction.id == PredictionEvaluation.prediction_id,
    ).where(
        PredictionEvaluation.run_id == state.current_run_id,
        PredictionEvaluation.provider_id == provider_id,
        Prediction.decision_forecast.is_(True),
    ).order_by(PredictionEvaluation.simulation_time.desc()).limit(30)).all()
    if not rows:
        return
    weights = [0.90 ** index for index in range(len(rows))]
    reliability = sum(max(0, 100 - evaluation.percentage_error) * weight for (evaluation, _), weight in zip(rows, weights)) / sum(weights)
    old = provider.forecast_reliability
    provider.forecast_reliability = round(reliability, 2)
    provider.failed_predictions = sum(not evaluation.successful for evaluation, _ in rows)
    db.add(ReputationHistory(
        run_id=state.current_run_id, provider_id=provider.id, contract_id=None,
        metric="Forecast reliability", old_value=old, new_value=provider.forecast_reliability,
        forecast_accuracy=round(reliability, 2), reason="Exponentially weighted accuracy of the 30 most recent decision forecasts",
        simulation_time=now,
    ))


def evaluate_due_predictions(db: Session, simulation_time: datetime) -> int:
    state = db.get(SimulationState, 1)
    evaluated_ids = select(PredictionEvaluation.prediction_id)
    predictions = db.scalars(select(Prediction).where(
        Prediction.run_id == state.current_run_id, Prediction.window_start <= simulation_time,
        Prediction.simulation_generated_at.is_not(None), Prediction.id.notin_(evaluated_ids),
    ).order_by(Prediction.window_start, Prediction.id)).all()
    affected_providers: set[int] = set()
    attributions: dict[str, int] = defaultdict(int)
    for prediction in predictions:
        actual = db.scalar(select(ResourceState).where(
            ResourceState.run_id == state.current_run_id, ResourceState.provider_id == prediction.provider_id,
            ResourceState.simulation_time <= prediction.window_start,
        ).order_by(ResourceState.simulation_time.desc(), ResourceState.id.desc()))
        if not actual:
            continue
        cpu_signed = prediction.predicted_cpu_usage - actual.cpu_usage
        ram_signed = prediction.predicted_ram_usage - actual.ram_usage
        cpu_error, ram_error = abs(cpu_signed), abs(ram_signed)
        cpu_ape = cpu_error / max(actual.cpu_usage, 1) * 100
        ram_ape = ram_error / max(actual.ram_usage, 1) * 100
        percentage_error = round((cpu_ape + ram_ape) / 2, 2)
        attribution = _attribution(db, prediction, actual, percentage_error)
        attributions[attribution] += 1
        impacted = attribution in {"Provider failure", "Traffic spike", "Workload drop"}
        db.add(PredictionEvaluation(
            run_id=state.current_run_id, prediction_id=prediction.id, provider_id=prediction.provider_id,
            simulation_time=prediction.window_start, actual_cpu_usage=actual.cpu_usage, actual_ram_usage=actual.ram_usage,
            cpu_absolute_error=round(cpu_error, 2), ram_absolute_error=round(ram_error, 2), percentage_error=percentage_error,
            forecast_bias=round((cpu_signed + ram_signed) / 2, 2), event_impacted=impacted,
            model_name=prediction.model_name, horizon_minutes=prediction.horizon_minutes,
            cpu_squared_error=round(cpu_error ** 2, 3), ram_squared_error=round(ram_error ** 2, 3),
            cpu_percentage_error=round(cpu_ape, 2), ram_percentage_error=round(ram_ape, 2),
            failure_attribution=attribution, training_insufficient=prediction.fallback_model is not None,
            successful=cpu_error <= prediction.uncertainty_cpu and ram_error <= prediction.uncertainty_ram,
        ))
        affected_providers.add(prediction.provider_id)
    db.flush()
    for provider_id in affected_providers:
        _update_reliability(db, state, provider_id, simulation_time)
    if predictions:
        record_event(db, "prediction.evaluated", f"Evaluated {len(predictions)} model forecasts against observed truth", simulation_time=simulation_time, details={"count": len(predictions), "attribution": dict(attributions)})
    return len(predictions)
