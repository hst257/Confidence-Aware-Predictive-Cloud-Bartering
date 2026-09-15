from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .models.enums import CollateralStatus, ContractStatus, PredictionKind


class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ResourceStateOut(OrmModel):
    id: int
    run_id: int | None = None
    cpu_usage: float
    ram_usage: float
    baseline_cpu: float = 0
    baseline_ram: float = 0
    usable_cpu: float = 0
    usable_ram: float = 0
    cpu_capacity_lost: float = 0
    ram_capacity_lost: float = 0
    random_noise_cpu: float = 0
    random_noise_ram: float = 0
    volatility: float = 0
    cpu_available: float = 0
    ram_available: float = 0
    reserved_future_cpu: float = 0
    reserved_future_ram: float = 0
    effective_future_cpu: float = 0
    effective_future_ram: float = 0
    simulation_time: datetime | None = None
    observed_at: datetime
    source: str


class PredictionOut(OrmModel):
    id: int
    provider_id: int
    run_id: int | None = None
    provider_name: str | None = None
    predicted_cpu_usage: float
    predicted_ram_usage: float
    predicted_cpu_spare: float
    predicted_ram_spare: float
    cpu_deficit: float
    ram_deficit: float
    safe_cpu_commitment: float
    safe_ram_commitment: float
    confidence: float
    window_start: datetime
    window_end: datetime
    generated_at: datetime
    simulation_generated_at: datetime | None = None
    horizon_minutes: int = 0
    cycle_id: str | None = None
    recent_volatility: float = 0
    model_name: str = "Legacy"
    decision_forecast: bool = True
    uncertainty_cpu: float = 0
    uncertainty_ram: float = 0
    fallback_model: str | None = None
    training_points: int = 0
    training_window_minutes: int = 0
    revision_number: int = 1
    model_metadata: dict | None = None
    kind: PredictionKind
    superseded: bool


class ProviderOut(OrmModel):
    id: int
    name: str
    total_cpu: float
    total_ram: float
    credit_balance: float
    sla_reputation: float
    forecast_reliability: float
    contribution_score: float
    successful_contracts: int
    failed_predictions: int
    locked_collateral: float = 0
    active_contracts: int = 0
    future_commitment_cpu: float = 0
    future_commitment_ram: float = 0
    current_state: ResourceStateOut | None = None
    latest_prediction: PredictionOut | None = None
    personality: str = ""
    current_volatility: float = 0
    active_event: str | None = None
    capacity_lost_cpu: float = 0
    capacity_lost_ram: float = 0


class CollateralOut(OrmModel):
    id: int
    amount: float
    status: CollateralStatus
    locked_at: datetime
    resolved_at: datetime | None


class ContractOut(OrmModel):
    id: int
    run_id: int | None = None
    provider_id: int
    provider_name: str
    consumer_id: int
    consumer_name: str
    prediction_id: int | None
    parent_contract_id: int | None
    cpu_amount: float
    ram_amount: float
    start_time: datetime
    end_time: datetime
    barter_cost: float
    prediction_confidence: float
    status: ContractStatus
    match_score: float
    selection_reason: str
    actual_cpu_spare: float | None
    actual_ram_spare: float | None
    collateral: CollateralOut | None
    created_at: datetime
    updated_at: datetime
    created_simulation_time: datetime | None = None
    barter_type: str = "Predictive"
    emergency_reason: str | None = None
    reaction_time_minutes: float | None = None


class MatchSuggestion(BaseModel):
    provider_id: int
    provider_name: str
    consumer_id: int
    consumer_name: str
    prediction_id: int
    demand_prediction_id: int = 0
    horizon_minutes: int = 0
    cpu_amount: float
    ram_amount: float
    requested_cpu: float
    requested_ram: float
    window_start: datetime
    window_end: datetime
    confidence: float
    forecast_reliability: float
    sla_reputation: float
    match_score: float
    barter_cost: float
    collateral: float
    safe_cpu_available: float = 0
    safe_ram_available: float = 0
    reserved_cpu: float = 0
    reserved_ram: float = 0
    contribution_score: float = 0
    selection_reason: str


class CreateContractRequest(BaseModel):
    provider_id: int
    consumer_id: int
    prediction_id: int
    cpu_amount: float = Field(gt=0)
    ram_amount: float = Field(ge=0)
    start_time: datetime
    end_time: datetime
    match_score: float = 0
    selection_reason: str = "Manually selected predictive match"


class SettlementRequest(BaseModel):
    actual_cpu_spare: float | None = Field(default=None, ge=0)
    actual_ram_spare: float | None = Field(default=None, ge=0)


class ReputationHistoryOut(OrmModel):
    id: int
    provider_id: int
    provider_name: str | None = None
    contract_id: int | None
    metric: str
    old_value: float
    new_value: float
    forecast_accuracy: float | None
    reason: str
    created_at: datetime
    simulation_time: datetime | None = None


class CreditTransactionOut(OrmModel):
    id: int
    provider_id: int
    provider_name: str | None = None
    contract_id: int | None
    amount: float
    transaction_type: str
    balance_after: float
    description: str
    created_at: datetime
    simulation_time: datetime | None = None


class RenegotiationEventOut(OrmModel):
    id: int
    original_contract_id: int
    reason: str
    old_cpu: float
    old_ram: float
    retained_cpu: float
    retained_ram: float
    replacement_contract_ids: list[int]
    created_at: datetime
    simulation_time: datetime | None = None


class EventOut(OrmModel):
    id: int
    event_type: str
    severity: str
    message: str
    provider_id: int | None
    contract_id: int | None
    details: dict
    created_at: datetime
    simulation_time: datetime | None = None


class SimulationSpeedRequest(BaseModel):
    speed: int


class SimulationStepRequest(BaseModel):
    minutes: int = Field(default=5, ge=1, le=240)


class SimulationConfigureRequest(BaseModel):
    scenario: str = "Normal"
    seed: int | None = Field(default=4281, ge=1, le=2_147_483_647)
    random_mode: bool = False
    forecast_model: str = "Auto"
    shadow_models: list[str] = Field(default_factory=lambda: ["Naive", "Moving Average", "Linear Trend", "Holt-Winters"])
    training_window_minutes: int = Field(default=360, ge=120, le=4320)
    bartering_strategy: str = Field(default="Confidence-Aware Predictive", pattern="^(Reactive Only|Predictive|Confidence-Aware Predictive)$")
    safety_margin_multiplier: float = Field(default=1.0, ge=0.25, le=3.0)
    model_selection_period_minutes: int = Field(default=60, ge=30, le=360)


class ExperimentComparisonRequest(BaseModel):
    run_ids: list[int] = Field(default_factory=list)


class InjectEventRequest(BaseModel):
    provider_id: int
    kind: str = Field(pattern="^(spike|drop|failure)$")
    severity: str = Field(default="warning", pattern="^(info|warning|critical)$")


class ActionResponse(BaseModel):
    message: str
    affected_contract_ids: list[int] = Field(default_factory=list)
