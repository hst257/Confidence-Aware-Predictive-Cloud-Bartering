"""Observation-only residual forecasting around the declared workload baseline.

Bounds use matured forecast errors where available, otherwise observed residual
spread plus a conservative cold-start floor. They are estimates, not guarantees.
No future workload observations or stochastic-event schedule is an input.
"""

from dataclasses import dataclass
from math import ceil, exp
from statistics import mean, pstdev


@dataclass(frozen=True)
class Estimate:
    mean: float
    lower: float
    upper: float
    window_upper: float


def estimate(history: list[tuple[float, float, float]], baselines: list[tuple[int, float]],
             errors: list[float], capacity: float, horizon: int, noise: float) -> Estimate:
    # History tuples are (relative observed minute, actual, baseline).
    recent = history[-30:]
    residuals = [actual - baseline for _, actual, baseline in recent]
    level = residuals[0] if residuals else 0.0
    for value in residuals[1:]:
        level = 0.8 * level + 0.2 * value
    tail = recent[-15:]
    slope = 0.0
    if len(tail) >= 3:
        xs = [point[0] for point in tail]
        ys = [point[1] - point[2] for point in tail]
        xbar, ybar = mean(xs), mean(ys)
        denominator = sum((x - xbar) ** 2 for x in xs)
        slope = sum((x - xbar) * (y - ybar) for x, y in zip(xs, ys)) / max(denominator, 1)
        slope = max(-capacity * .02, min(capacity * .02, slope))
    bias = mean(errors[-60:]) * .5 if len(errors) >= 8 else 0.0
    floor = capacity * (.012 + .006 * noise) * (1 + horizon / 240)
    if len(errors) >= 8:
        absolute = sorted(abs(error - bias) for error in errors[-60:])
        margin = max(floor, absolute[max(0, ceil(.9 * len(absolute)) - 1)])
    else:
        margin = max(floor, 1.645 * (pstdev(residuals) if len(residuals) >= 3 else 0))

    def forecast(offset: int, baseline: float) -> float:
        ahead = horizon + offset
        adjustment = level * exp(-ahead / 45) + slope * min(ahead, 15) * exp(-ahead / 30) + bias
        return round(max(0, min(capacity * 1.65, baseline + adjustment)), 2)

    center = forecast(0, baselines[0][1])
    peak = max(forecast(offset, baseline) for offset, baseline in baselines)
    return Estimate(center, round(max(0, center - margin), 2), round(center + margin, 2), round(peak + margin, 2))
