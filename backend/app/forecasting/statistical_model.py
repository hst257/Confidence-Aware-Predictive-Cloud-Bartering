from math import sqrt
from statistics import mean

from .base_model import ForecastModel, ForecastResult
from .feature_engineering import standard_deviation


class HoltWintersForecastModel(ForecastModel):
    """Dependency-free additive Holt-Winters forecaster.

    The project retrains on rolling history. A level and trend are fitted with
    Holt-Winters recurrences; uncertainty comes from one-step residuals and grows with
    the forecast horizon. This is intentionally transparent and dependency-free.
    """

    name = "Holt-Winters"
    minimum_points = 120
    alpha = 0.32
    beta = 0.10
    gamma = 0.18
    season_length = 60

    @classmethod
    def _fit_series(cls, values: list[float]) -> tuple[float, float, list[float], float]:
        period = cls.season_length
        level = mean(values[:period])
        trend = sum(values[period + index] - values[index] for index in range(period)) / (period * period)
        seasonals = [values[index] - level for index in range(period)]
        residuals: list[float] = []
        for index, value in enumerate(values):
            season_index = index % period
            previous_season = seasonals[season_index]
            predicted = level + trend + previous_season
            residuals.append(value - predicted)
            previous_level = level
            level = cls.alpha * (value - previous_season) + (1 - cls.alpha) * (level + trend)
            trend = cls.beta * (level - previous_level) + (1 - cls.beta) * trend
            seasonals[season_index] = cls.gamma * (value - level) + (1 - cls.gamma) * previous_season
        return level, trend, seasonals, standard_deviation(residuals)

    def _fit(self) -> None:
        window = self.history[-min(360, len(self.history)):]
        self.cpu_level, self.cpu_trend, self.cpu_seasonals, self.cpu_sigma = self._fit_series([item.cpu for item in window])
        self.ram_level, self.ram_trend, self.ram_seasonals, self.ram_sigma = self._fit_series([item.ram for item in window])
        self.series_length = len(window)

    def predict(self, horizon_minutes: int) -> ForecastResult:
        scale = sqrt(1 + horizon_minutes / 30)
        seasonal_index = (self.series_length + horizon_minutes - 1) % self.season_length
        return ForecastResult(
            self.cpu_level + self.cpu_trend * horizon_minutes + self.cpu_seasonals[seasonal_index],
            self.ram_level + self.ram_trend * horizon_minutes + self.ram_seasonals[seasonal_index],
            max(1.0, self.cpu_sigma) * scale,
            max(1.5, self.ram_sigma) * scale,
            {"method": "additive Holt-Winters", "alpha": self.alpha, "beta": self.beta, "gamma": self.gamma, "season_length": self.season_length, "cpu_trend": self.cpu_trend, "ram_trend": self.ram_trend},
        )
