from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class Observation:
    timestamp: datetime
    cpu: float
    ram: float


@dataclass(frozen=True)
class ForecastResult:
    cpu: float
    ram: float
    uncertainty_cpu: float
    uncertainty_ram: float
    metadata: dict = field(default_factory=dict)


class ForecastModel(ABC):
    """Common interface. Implementations receive historical observations only."""

    name = "Base"
    minimum_points = 1

    def __init__(self) -> None:
        self.history: list[Observation] = []

    def train(self, history: list[Observation]) -> "ForecastModel":
        if not history:
            raise ValueError("At least one historical observation is required")
        self.history = list(history)
        self._fit()
        return self

    def _fit(self) -> None:
        return None

    @abstractmethod
    def predict(self, horizon_minutes: int) -> ForecastResult:
        raise NotImplementedError

    def evaluate(self, actual_cpu: float, actual_ram: float, forecast: ForecastResult) -> dict:
        return {
            "cpu_error": forecast.cpu - actual_cpu,
            "ram_error": forecast.ram - actual_ram,
        }
