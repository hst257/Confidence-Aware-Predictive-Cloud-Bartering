from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import (
    Prediction,
    PredictionEvaluation,
    PredictionKind,
    Provider,
    ReputationHistory,
    ResourceState,
    SimulationState,
    StochasticEvent,
)
from ..services.event_service import record_event
from .random_manager import normal
from .workload_profiles import personality, workload_at


INITIAL_FORECASTS = {
    "Cloud A": {"cpu": 110, "ram": 185, "confidence": 91},
    "Cloud B": {"cpu": 45, "ram": 120, "confidence": 88},
    "Cloud C": {"cpu": 75, "ram": 100, "confidence": 82},
    "Cloud D": {"cpu": 82, "ram": 118, "confidence": 74},
}


def _build_prediction(
    provider: Provider,
    cpu_usage: float,
    ram_usage: float,
    confidence: float,
    window_start: datetime,
    window_end: datetime,
    kind: PredictionKind,
    total_cpu: float | None = None,
    total_ram: float | None = None,
    run_id: int | None = None,
    volatility: float = 0,
) -> Prediction:
    cpu_capacity = provider.total_cpu if total_cpu is None else total_cpu
    ram_capacity = provider.total_ram if total_ram is None else total_ram
    cpu_spare = max(cpu_capacity - cpu_usage, 0)
    ram_spare = max(ram_capacity - ram_usage, 0)
    confidence_factor = confidence / 100
    reliability_factor = provider.forecast_reliability / 100
    return Prediction(
        provider_id=provider.id,
        run_id=run_id,
        predicted_cpu_usage=cpu_usage,
        predicted_ram_usage=ram_usage,
        predicted_cpu_spare=cpu_spare,
        predicted_ram_spare=ram_spare,
        cpu_deficit=max(cpu_usage - cpu_capacity, 0),
        ram_deficit=max(ram_usage - ram_capacity, 0),
        safe_cpu_commitment=round(cpu_spare * confidence_factor * reliability_factor, 2),
        safe_ram_commitment=round(ram_spare * confidence_factor * reliability_factor, 2),
        confidence=confidence,
        window_start=window_start,
        window_end=window_end,
        kind=kind,
        recent_volatility=volatility,
    )


def generate_initial_predictions(db: Session) -> list[Prediction]:
    state = db.get(SimulationState, 1)
    run_id = state.current_run_id if state else None
    current = db.scalars(select(Prediction).where(Prediction.run_id == run_id, Prediction.superseded.is_(False))).all()
    for prediction in current:
        prediction.superseded = True

    now = datetime.utcnow().replace(second=0, microsecond=0)
    window_start = now + timedelta(hours=4)
    window_end = now + timedelta(hours=6)
    providers = db.scalars(select(Provider).order_by(Provider.id)).all()
    predictions: list[Prediction] = []
    for provider in providers:
        forecast = INITIAL_FORECASTS[provider.name]
        prediction = _build_prediction(
            provider,
            forecast["cpu"],
            forecast["ram"],
            forecast["confidence"],
            window_start,
            window_end,
            PredictionKind.INITIAL,
            run_id=run_id,
        )
        db.add(prediction)
        db.flush()
        predictions.append(prediction)
        if prediction.cpu_deficit or prediction.ram_deficit:
            message = (
                f"{provider.name} predicted a {prediction.cpu_deficit:g} CPU / "
                f"{prediction.ram_deficit:g} GB deficit at {window_start:%H:%M}"
            )
            event_type = "prediction.deficit"
            severity = "warning"
        else:
            message = (
                f"{provider.name} predicted {prediction.predicted_cpu_spare:g} CPU / "
                f"{prediction.predicted_ram_spare:g} GB surplus ({prediction.confidence:g}% confidence)"
            )
            event_type = "prediction.surplus"
            severity = "info"
        record_event(
            db,
            event_type,
            message,
            severity=severity,
            provider_id=provider.id,
            details={"prediction_id": prediction.id, "confidence": prediction.confidence},
        )
    db.commit()
    return predictions


def generate_revised_cloud_b_prediction(db: Session) -> Prediction:
    state = db.get(SimulationState, 1)
    run_id = state.current_run_id if state else None
    provider = db.scalar(select(Provider).where(Provider.name == "Cloud B"))
    current = db.scalar(
        select(Prediction)
        .where(Prediction.run_id == run_id, Prediction.provider_id == provider.id, Prediction.superseded.is_(False))
        .order_by(Prediction.generated_at.desc(), Prediction.id.desc())
    )
    if not current:
        raise ValueError("Generate initial predictions before re-evaluating")
    if current.kind == PredictionKind.REVISED:
        return current
    current.superseded = True
    revised = _build_prediction(
        provider,
        cpu_usage=80,
        ram_usage=241,
        confidence=72,
        window_start=current.window_start,
        window_end=current.window_end,
        kind=PredictionKind.REVISED,
        run_id=run_id,
    )
    db.add(revised)
    db.flush()
    record_event(
        db,
        "prediction.revised",
        "Cloud B forecast changed: available capacity fell to 20 CPU / 15 GB RAM",
        severity="warning",
        provider_id=provider.id,
        details={"old_prediction_id": current.id, "new_prediction_id": revised.id},
    )
    return revised


def generate_simulation_predictions(db: Session, simulation_time: datetime) -> list[Prediction]:
    """Create deterministic, intentionally imperfect Phase 3 forecasts.

    The predictor knows each provider's baseline pattern and observations up to
    ``simulation_time``. It never reads future resource samples or future
    stochastic events, so traffic spikes and failures can invalidate it.
    """
    settings = get_settings()
    state = db.get(SimulationState, 1)
    if not state or not state.current_run_id:
        return []

    providers = db.scalars(select(Provider).order_by(Provider.id)).all()
    latest_by_provider = {
        provider.id: db.scalar(select(ResourceState).where(
            ResourceState.run_id == state.current_run_id,
            ResourceState.provider_id == provider.id,
            ResourceState.simulation_time <= simulation_time,
        ).order_by(ResourceState.simulation_time.desc(), ResourceState.id.desc()))
        for provider in providers
    }
    available_provider_ids = {provider_id for provider_id, item in latest_by_provider.items() if item is not None}
    if not available_provider_ids:
        record_event(
            db,
            "prediction.cycle_skipped",
            "Prediction cycle skipped because this run has no observations yet",
            severity="warning",
            simulation_time=simulation_time,
        )
        return []

    for active in db.scalars(select(Prediction).where(
        Prediction.run_id == state.current_run_id,
        Prediction.provider_id.in_(available_provider_ids),
        Prediction.superseded.is_(False),
    )).all():
        active.superseded = True

    cycle_id = f"R{state.current_run_id}-" + simulation_time.strftime("D%j-%H%M")
    generated: list[Prediction] = []
    record_event(
        db,
        "prediction.cycle_started",
        f"Simulated prediction cycle started for {len(settings.prediction_horizons)} future horizons",
        simulation_time=simulation_time,
        details={"cycle_id": cycle_id, "horizons": settings.prediction_horizons},
    )

    for provider in providers:
        latest = latest_by_provider[provider.id]
        if latest is None:
            continue
        profile = personality(provider.name)
        for horizon in settings.prediction_horizons:
            target = simulation_time + timedelta(minutes=horizon)
            baseline = workload_at(provider.name, target)
            baseline_weight = min(0.90, 0.65 + horizon / 600)
            volatility = max(0.0, latest.volatility)
            error_scale = 0.012 + profile["noise"] * 0.008 + min(volatility, 12) * 0.0025 + horizon / 240 * 0.025
            key = (provider.name, simulation_time.strftime("%Y-%m-%dT%H:%M"), horizon)
            predicted_cpu = baseline.cpu * baseline_weight + latest.cpu_usage * (1 - baseline_weight)
            predicted_ram = baseline.ram * baseline_weight + latest.ram_usage * (1 - baseline_weight)
            predicted_cpu += normal(state.seed, *key, "forecast-cpu") * provider.total_cpu * error_scale
            predicted_ram += normal(state.seed, *key, "forecast-ram") * provider.total_ram * error_scale
            predicted_cpu = round(max(0, min(provider.total_cpu * 1.65, predicted_cpu)), 2)
            predicted_ram = round(max(0, min(provider.total_ram * 1.65, predicted_ram)), 2)

            usable_cpu = latest.usable_cpu or provider.total_cpu
            usable_ram = latest.usable_ram or provider.total_ram
            cpu_spare = round(max(0, usable_cpu - predicted_cpu), 2)
            ram_spare = round(max(0, usable_ram - predicted_ram), 2)
            horizon_penalty = horizon / 60 * 2.8
            volatility_penalty = min(18, volatility * 1.8)
            reliability_adjustment = (provider.forecast_reliability - 80) * 0.18
            confidence = round(max(45, min(98, profile["base_confidence"] - horizon_penalty - volatility_penalty + reliability_adjustment)), 2)
            confidence_factor = confidence / 100
            reliability_factor = provider.forecast_reliability / 100
            prediction = Prediction(
                run_id=state.current_run_id,
                provider_id=provider.id,
                predicted_cpu_usage=predicted_cpu,
                predicted_ram_usage=predicted_ram,
                predicted_cpu_spare=cpu_spare,
                predicted_ram_spare=ram_spare,
                cpu_deficit=round(max(0, predicted_cpu - usable_cpu), 2),
                ram_deficit=round(max(0, predicted_ram - usable_ram), 2),
                safe_cpu_commitment=round(cpu_spare * confidence_factor * reliability_factor, 2),
                safe_ram_commitment=round(ram_spare * confidence_factor * reliability_factor, 2),
                confidence=confidence,
                window_start=target,
                window_end=target + timedelta(minutes=settings.contract_duration_minutes),
                simulation_generated_at=simulation_time,
                horizon_minutes=horizon,
                cycle_id=cycle_id,
                recent_volatility=volatility,
                kind=PredictionKind.INITIAL,
            )
            db.add(prediction)
            db.flush()
            generated.append(prediction)
            if horizon == settings.planning_horizon_minutes:
                deficit = prediction.cpu_deficit > 0 or prediction.ram_deficit > 0
                record_event(
                    db,
                    "prediction.deficit" if deficit else "prediction.surplus",
                    (
                        f"{provider.name} predicted a future {'deficit' if deficit else 'surplus'} at "
                        f"{target:%H:%M} with {confidence:g}% confidence"
                    ),
                    severity="warning" if deficit else "info",
                    provider_id=provider.id,
                    simulation_time=simulation_time,
                    details={
                        "prediction_id": prediction.id,
                        "horizon_minutes": horizon,
                        "confidence": confidence,
                        "future_events_hidden": True,
                    },
                )
    return generated


def _event_impacted(db: Session, prediction: Prediction) -> bool:
    return db.scalar(select(StochasticEvent.id).where(
        StochasticEvent.run_id == prediction.run_id,
        StochasticEvent.provider_id == prediction.provider_id,
        StochasticEvent.start_time <= prediction.window_start,
        StochasticEvent.end_time > prediction.window_start,
    ).limit(1)) is not None


def _update_forecast_reliability(db: Session, state: SimulationState, provider_id: int, now: datetime) -> None:
    provider = db.get(Provider, provider_id)
    evaluations = db.scalars(select(PredictionEvaluation).where(
        PredictionEvaluation.run_id == state.current_run_id,
        PredictionEvaluation.provider_id == provider_id,
    ).order_by(PredictionEvaluation.simulation_time.desc()).limit(20)).all()
    if not provider or not evaluations:
        return
    rolling_accuracy = sum(max(0, 100 - item.percentage_error) for item in evaluations) / len(evaluations)
    old = provider.forecast_reliability
    learning_rate = get_settings().reputation_learning_rate
    provider.forecast_reliability = round(old * (1 - learning_rate) + rolling_accuracy * learning_rate, 2)
    db.add(ReputationHistory(
        run_id=state.current_run_id,
        provider_id=provider.id,
        contract_id=None,
        metric="Forecast reliability",
        old_value=old,
        new_value=provider.forecast_reliability,
        forecast_accuracy=round(rolling_accuracy, 2),
        reason="Rolling accuracy of recent simulated predictions",
        simulation_time=now,
    ))


def evaluate_due_predictions(db: Session, simulation_time: datetime) -> int:
    """Evaluate Phase 3 predictions with MAE, percentage error, and success."""
    state = db.get(SimulationState, 1)
    if not state or not state.current_run_id:
        return 0
    evaluated_ids = select(PredictionEvaluation.prediction_id)
    predictions = db.scalars(select(Prediction).where(
        Prediction.run_id == state.current_run_id,
        Prediction.window_start <= simulation_time,
        Prediction.simulation_generated_at.is_not(None),
        Prediction.id.notin_(evaluated_ids),
    ).order_by(Prediction.window_start, Prediction.id)).all()
    affected_providers: set[int] = set()
    failed_by_provider: dict[int, int] = {}
    evaluated = 0
    for prediction in predictions:
        actual = db.scalar(select(ResourceState).where(
            ResourceState.run_id == state.current_run_id,
            ResourceState.provider_id == prediction.provider_id,
            ResourceState.simulation_time <= prediction.window_start,
        ).order_by(ResourceState.simulation_time.desc(), ResourceState.id.desc()))
        if not actual:
            continue
        cpu_signed = prediction.predicted_cpu_usage - actual.cpu_usage
        ram_signed = prediction.predicted_ram_usage - actual.ram_usage
        cpu_error = abs(cpu_signed)
        ram_error = abs(ram_signed)
        cpu_percentage = cpu_error / max(actual.cpu_usage, 1) * 100
        ram_percentage = ram_error / max(actual.ram_usage, 1) * 100
        percentage_error = round((cpu_percentage + ram_percentage) / 2, 2)
        successful = percentage_error <= max(5, 100 - prediction.confidence)
        db.add(PredictionEvaluation(
            run_id=state.current_run_id,
            prediction_id=prediction.id,
            provider_id=prediction.provider_id,
            simulation_time=prediction.window_start,
            actual_cpu_usage=actual.cpu_usage,
            actual_ram_usage=actual.ram_usage,
            cpu_absolute_error=round(cpu_error, 2),
            ram_absolute_error=round(ram_error, 2),
            percentage_error=percentage_error,
            forecast_bias=round((cpu_signed + ram_signed) / 2, 2),
            event_impacted=_event_impacted(db, prediction),
            successful=successful,
        ))
        affected_providers.add(prediction.provider_id)
        if not successful:
            failed_by_provider[prediction.provider_id] = failed_by_provider.get(prediction.provider_id, 0) + 1
        evaluated += 1
    db.flush()
    for provider_id in affected_providers:
        provider = db.get(Provider, provider_id)
        if provider:
            provider.failed_predictions += failed_by_provider.get(provider_id, 0)
        _update_forecast_reliability(db, state, provider_id, simulation_time)
    if evaluated:
        record_event(
            db,
            "prediction.evaluated",
            f"Evaluated {evaluated} simulated predictions against observed workload",
            simulation_time=simulation_time,
            details={"count": evaluated},
        )
    return evaluated
