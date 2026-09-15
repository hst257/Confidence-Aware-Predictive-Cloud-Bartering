from math import sqrt

from .base_model import ForecastModel, ForecastResult
from .feature_engineering import standard_deviation


class MovingAverageForecastModel(ForecastModel):
    name = "Moving Average"
    minimum_points = 8

    def _fit(self) -> None:
        window = self.history[-min(30, len(self.history)):]
        weights = list(range(1, len(window) + 1))
        total = sum(weights)
        self.cpu_level = sum(item.cpu * weight for item, weight in zip(window, weights)) / total
        self.ram_level = sum(item.ram * weight for item, weight in zip(window, weights)) / total
        self.cpu_sigma = standard_deviation([item.cpu - self.cpu_level for item in window]) or max(1.5, self.cpu_level * 0.05)
        self.ram_sigma = standard_deviation([item.ram - self.ram_level for item in window]) or max(2.0, self.ram_level * 0.05)

    def predict(self, horizon_minutes: int) -> ForecastResult:
        scale = sqrt(1 + horizon_minutes / 60)
        return ForecastResult(self.cpu_level, self.ram_level, self.cpu_sigma * scale, self.ram_sigma * scale, {"method": "weighted 30-minute moving average", "cpu_trend": 0, "ram_trend": 0})
