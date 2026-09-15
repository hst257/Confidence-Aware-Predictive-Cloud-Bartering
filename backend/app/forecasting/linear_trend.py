from math import sqrt

from .base_model import ForecastModel, ForecastResult
from .feature_engineering import linear_fit


class LinearTrendForecastModel(ForecastModel):
    name = "Linear Trend"
    minimum_points = 12

    def _fit(self) -> None:
        window = self.history[-min(120, len(self.history)):]
        self.origin = window[0].timestamp
        self.last_time = (window[-1].timestamp - self.origin).total_seconds() / 60
        self.cpu_intercept, self.cpu_slope, self.cpu_sigma = linear_fit(window, "cpu")
        self.ram_intercept, self.ram_slope, self.ram_sigma = linear_fit(window, "ram")

    def predict(self, horizon_minutes: int) -> ForecastResult:
        target = self.last_time + horizon_minutes
        scale = sqrt(1 + horizon_minutes / 45)
        return ForecastResult(
            self.cpu_intercept + self.cpu_slope * target,
            self.ram_intercept + self.ram_slope * target,
            max(1.0, self.cpu_sigma) * scale,
            max(1.5, self.ram_sigma) * scale,
            {"method": "rolling least-squares trend", "cpu_trend": self.cpu_slope, "ram_trend": self.ram_slope},
        )
