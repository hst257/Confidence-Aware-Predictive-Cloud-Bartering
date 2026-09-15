from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Prediction, PredictionKind, Provider, SimulationState
from ..services.event_service import record_event


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
    """Compatibility entry point; Phase 4 logic lives in forecasting/."""
    from ..forecasting.model_manager import generate_forecasts

    return generate_forecasts(db, simulation_time)
