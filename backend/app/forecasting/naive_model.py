from math import sqrt

from .base_model import ForecastModel, ForecastResult
from .feature_engineering import recent_changes, standard_deviation


class NaiveForecastModel(ForecastModel):
    name = "Naive"
    minimum_points = 1

    def predict(self, horizon_minutes: int) -> ForecastResult:
        last = self.history[-1]
        cpu_sigma = standard_deviation(recent_changes(self.history[-30:], "cpu")) or max(2.0, last.cpu * 0.08)
        ram_sigma = standard_deviation(recent_changes(self.history[-30:], "ram")) or max(3.0, last.ram * 0.08)
        scale = sqrt(max(1.0, horizon_minutes / 15))
        return ForecastResult(last.cpu, last.ram, cpu_sigma * scale, ram_sigma * scale, {"method": "last observation", "cpu_trend": 0, "ram_trend": 0})
