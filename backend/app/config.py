from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Confidence-Aware Cloud Barter API"
    database_url: str = "postgresql+psycopg://cloud_barter:cloud_barter@localhost:55432/cloud_barter"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Phase 1 economic and reputation policy knobs.
    collateral_rate: float = 0.16
    cpu_credit_rate: float = 1.5
    ram_credit_rate: float = 0.6
    reliability_weight: float = 0.23
    confidence_weight: float = 0.25
    sla_weight: float = 0.17
    capacity_weight: float = 0.20
    contribution_weight: float = 0.08
    credit_balance_weight: float = 0.07
    reputation_learning_rate: float = 0.30
    success_sla_bonus: float = 0.5
    failure_sla_penalty: float = 6.0
    failure_reliability_penalty: float = 10.0

    # Phase 2 simulation cadence. Logical time is intentionally independent
    # from database and browser refresh frequency.
    simulation_start_iso: str = "2026-01-01T08:00:00"
    simulation_tick_real_seconds: float = 0.25
    resource_sample_seconds: int = 60
    prediction_interval_minutes: int = 30
    prediction_horizons_minutes: str = "30,60,120,240"
    planning_horizon_minutes: int = 240
    contract_duration_minutes: int = 60
    contract_planning_cooldown_minutes: int = 180
    step_forward_minutes: int = 5
    max_history_points: int = 720

    @property
    def prediction_horizons(self) -> list[int]:
        return [int(value.strip()) for value in self.prediction_horizons_minutes.split(",") if value.strip()]

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
