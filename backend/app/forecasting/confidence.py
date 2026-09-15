from __future__ import annotations


CONFIDENCE_FORMULA = (
    "100 − [40% recent model percentage error + 30% normalized forecast interval "
    "+ 20% recent workload volatility + 10% horizon risk], with a 12-point "
    "insufficient-history penalty; clamped to 35–97%."
)


def confidence_from_uncertainty(
    *, uncertainty_cpu: float, uncertainty_ram: float, total_cpu: float, total_ram: float,
    recent_error: float, volatility: float, horizon_minutes: int, insufficient_history: bool,
) -> float:
    uncertainty_percent = ((uncertainty_cpu / max(total_cpu, 1)) + (uncertainty_ram / max(total_ram, 1))) * 50
    horizon_risk = min(30.0, horizon_minutes / 240 * 30)
    risk = 0.40 * recent_error + 0.30 * uncertainty_percent + 0.20 * min(40.0, volatility) + 0.10 * horizon_risk
    if insufficient_history:
        risk += 12
    return round(max(35.0, min(97.0, 100 - risk)), 1)
