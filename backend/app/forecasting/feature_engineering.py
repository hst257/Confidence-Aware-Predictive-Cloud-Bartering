from __future__ import annotations

from math import sqrt

from .base_model import Observation


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def standard_deviation(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    center = mean(values)
    return sqrt(sum((value - center) ** 2 for value in values) / (len(values) - 1))


def linear_fit(history: list[Observation], resource: str) -> tuple[float, float, float]:
    """Return intercept, units-per-minute slope, and residual deviation."""
    origin = history[0].timestamp
    xs = [(item.timestamp - origin).total_seconds() / 60 for item in history]
    ys = [getattr(item, resource) for item in history]
    x_mean, y_mean = mean(xs), mean(ys)
    denominator = sum((x - x_mean) ** 2 for x in xs)
    slope = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys)) / denominator if denominator else 0.0
    intercept = y_mean - slope * x_mean
    residuals = [y - (intercept + slope * x) for x, y in zip(xs, ys)]
    return intercept, slope, standard_deviation(residuals)


def recent_changes(history: list[Observation], resource: str) -> list[float]:
    values = [getattr(item, resource) for item in history]
    return [after - before for before, after in zip(values, values[1:])]
