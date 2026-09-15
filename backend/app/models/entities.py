from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base
from .enums import CollateralStatus, ContractStatus, CreditTransactionType, PredictionKind


def utcnow() -> datetime:
    return datetime.utcnow()


class Provider(Base):
    __tablename__ = "providers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    total_cpu: Mapped[float] = mapped_column(Float)
    total_ram: Mapped[float] = mapped_column(Float)
    credit_balance: Mapped[float] = mapped_column(Float, default=0)
    sla_reputation: Mapped[float] = mapped_column(Float, default=80)
    forecast_reliability: Mapped[float] = mapped_column(Float, default=80)
    contribution_score: Mapped[float] = mapped_column(Float, default=0)
    successful_contracts: Mapped[int] = mapped_column(Integer, default=0)
    failed_predictions: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    resource_states: Mapped[list[ResourceState]] = relationship(back_populates="provider", cascade="all, delete-orphan")
    predictions: Mapped[list[Prediction]] = relationship(back_populates="provider", cascade="all, delete-orphan")


class ResourceState(Base):
    __tablename__ = "resource_states"

    id: Mapped[int] = mapped_column(primary_key=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("simulation_runs.id"), nullable=True, index=True)
    cpu_usage: Mapped[float] = mapped_column(Float)
    ram_usage: Mapped[float] = mapped_column(Float)
    baseline_cpu: Mapped[float] = mapped_column(Float, default=0)
    baseline_ram: Mapped[float] = mapped_column(Float, default=0)
    usable_cpu: Mapped[float] = mapped_column(Float, default=0)
    usable_ram: Mapped[float] = mapped_column(Float, default=0)
    cpu_capacity_lost: Mapped[float] = mapped_column(Float, default=0)
    ram_capacity_lost: Mapped[float] = mapped_column(Float, default=0)
    random_noise_cpu: Mapped[float] = mapped_column(Float, default=0)
    random_noise_ram: Mapped[float] = mapped_column(Float, default=0)
    volatility: Mapped[float] = mapped_column(Float, default=0)
    cpu_available: Mapped[float] = mapped_column(Float, default=0)
    ram_available: Mapped[float] = mapped_column(Float, default=0)
    reserved_future_cpu: Mapped[float] = mapped_column(Float, default=0)
    reserved_future_ram: Mapped[float] = mapped_column(Float, default=0)
    effective_future_cpu: Mapped[float] = mapped_column(Float, default=0)
    effective_future_ram: Mapped[float] = mapped_column(Float, default=0)
    simulation_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    source: Mapped[str] = mapped_column(String(40), default="simulation")

    provider: Mapped[Provider] = relationship(back_populates="resource_states")


class Prediction(Base):
    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(primary_key=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("simulation_runs.id"), nullable=True, index=True)
    predicted_cpu_usage: Mapped[float] = mapped_column(Float)
    predicted_ram_usage: Mapped[float] = mapped_column(Float)
    predicted_cpu_spare: Mapped[float] = mapped_column(Float)
    predicted_ram_spare: Mapped[float] = mapped_column(Float)
    cpu_deficit: Mapped[float] = mapped_column(Float, default=0)
    ram_deficit: Mapped[float] = mapped_column(Float, default=0)
    safe_cpu_commitment: Mapped[float] = mapped_column(Float, default=0)
    safe_ram_commitment: Mapped[float] = mapped_column(Float, default=0)
    confidence: Mapped[float] = mapped_column(Float)
    window_start: Mapped[datetime] = mapped_column(DateTime, index=True)
    window_end: Mapped[datetime] = mapped_column(DateTime)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    simulation_generated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    horizon_minutes: Mapped[int] = mapped_column(Integer, default=0)
    cycle_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    recent_volatility: Mapped[float] = mapped_column(Float, default=0)
    model_name: Mapped[str] = mapped_column(String(40), default="Legacy", index=True)
    decision_forecast: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    uncertainty_cpu: Mapped[float] = mapped_column(Float, default=0)
    uncertainty_ram: Mapped[float] = mapped_column(Float, default=0)
    fallback_model: Mapped[str | None] = mapped_column(String(40), nullable=True)
    training_points: Mapped[int] = mapped_column(Integer, default=0)
    training_window_minutes: Mapped[int] = mapped_column(Integer, default=0)
    revision_number: Mapped[int] = mapped_column(Integer, default=1)
    model_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    kind: Mapped[PredictionKind] = mapped_column(Enum(PredictionKind), default=PredictionKind.INITIAL)
    superseded: Mapped[bool] = mapped_column(default=False)

    provider: Mapped[Provider] = relationship(back_populates="predictions")


class BarterContract(Base):
    __tablename__ = "barter_contracts"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("simulation_runs.id"), nullable=True, index=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id"), index=True)
    consumer_id: Mapped[int] = mapped_column(ForeignKey("providers.id"), index=True)
    prediction_id: Mapped[int | None] = mapped_column(ForeignKey("predictions.id"), nullable=True)
    parent_contract_id: Mapped[int | None] = mapped_column(ForeignKey("barter_contracts.id"), nullable=True)
    cpu_amount: Mapped[float] = mapped_column(Float)
    ram_amount: Mapped[float] = mapped_column(Float)
    start_time: Mapped[datetime] = mapped_column(DateTime, index=True)
    end_time: Mapped[datetime] = mapped_column(DateTime)
    barter_cost: Mapped[float] = mapped_column(Float)
    prediction_confidence: Mapped[float] = mapped_column(Float)
    status: Mapped[ContractStatus] = mapped_column(Enum(ContractStatus), default=ContractStatus.PROPOSED, index=True)
    match_score: Mapped[float] = mapped_column(Float, default=0)
    selection_reason: Mapped[str] = mapped_column(Text, default="")
    actual_cpu_spare: Mapped[float | None] = mapped_column(Float, nullable=True)
    actual_ram_spare: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    created_simulation_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    barter_type: Mapped[str] = mapped_column(String(24), default="Predictive", index=True)
    emergency_reason: Mapped[str | None] = mapped_column(String(240), nullable=True)
    reaction_time_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)

    provider: Mapped[Provider] = relationship(foreign_keys=[provider_id])
    consumer: Mapped[Provider] = relationship(foreign_keys=[consumer_id])
    prediction: Mapped[Prediction | None] = relationship()
    parent_contract: Mapped[BarterContract | None] = relationship(remote_side=[id])
    collateral: Mapped[Collateral | None] = relationship(back_populates="contract", uselist=False, cascade="all, delete-orphan")


class CreditTransaction(Base):
    __tablename__ = "credit_transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("simulation_runs.id"), nullable=True, index=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id"), index=True)
    contract_id: Mapped[int | None] = mapped_column(ForeignKey("barter_contracts.id"), nullable=True)
    amount: Mapped[float] = mapped_column(Float)
    transaction_type: Mapped[CreditTransactionType] = mapped_column(Enum(CreditTransactionType))
    balance_after: Mapped[float] = mapped_column(Float)
    description: Mapped[str] = mapped_column(String(240))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    simulation_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)

    provider: Mapped[Provider] = relationship()
    contract: Mapped[BarterContract | None] = relationship()


class Collateral(Base):
    __tablename__ = "collaterals"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("simulation_runs.id"), nullable=True, index=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey("barter_contracts.id", ondelete="CASCADE"), unique=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id"))
    amount: Mapped[float] = mapped_column(Float)
    status: Mapped[CollateralStatus] = mapped_column(Enum(CollateralStatus), default=CollateralStatus.LOCKED)
    locked_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    contract: Mapped[BarterContract] = relationship(back_populates="collateral")
    provider: Mapped[Provider] = relationship()


class ReputationHistory(Base):
    __tablename__ = "reputation_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("simulation_runs.id"), nullable=True, index=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id"), index=True)
    contract_id: Mapped[int | None] = mapped_column(ForeignKey("barter_contracts.id"), nullable=True)
    metric: Mapped[str] = mapped_column(String(60))
    old_value: Mapped[float] = mapped_column(Float)
    new_value: Mapped[float] = mapped_column(Float)
    forecast_accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)
    reason: Mapped[str] = mapped_column(String(240))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    simulation_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)

    provider: Mapped[Provider] = relationship()


class RenegotiationEvent(Base):
    __tablename__ = "renegotiation_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("simulation_runs.id"), nullable=True, index=True)
    original_contract_id: Mapped[int] = mapped_column(ForeignKey("barter_contracts.id"), index=True)
    reason: Mapped[str] = mapped_column(Text)
    old_cpu: Mapped[float] = mapped_column(Float)
    old_ram: Mapped[float] = mapped_column(Float)
    retained_cpu: Mapped[float] = mapped_column(Float)
    retained_ram: Mapped[float] = mapped_column(Float)
    replacement_contract_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    simulation_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)

    original_contract: Mapped[BarterContract] = relationship()


class EventLog(Base):
    __tablename__ = "event_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("simulation_runs.id"), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(60), index=True)
    severity: Mapped[str] = mapped_column(String(20), default="info")
    message: Mapped[str] = mapped_column(Text)
    provider_id: Mapped[int | None] = mapped_column(ForeignKey("providers.id"), nullable=True)
    contract_id: Mapped[int | None] = mapped_column(ForeignKey("barter_contracts.id"), nullable=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    simulation_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)


class PredictionEvaluation(Base):
    __tablename__ = "prediction_evaluations"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("simulation_runs.id"), nullable=True, index=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id", ondelete="CASCADE"), unique=True, index=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id", ondelete="CASCADE"), index=True)
    simulation_time: Mapped[datetime] = mapped_column(DateTime, index=True)
    actual_cpu_usage: Mapped[float] = mapped_column(Float)
    actual_ram_usage: Mapped[float] = mapped_column(Float)
    cpu_absolute_error: Mapped[float] = mapped_column(Float)
    ram_absolute_error: Mapped[float] = mapped_column(Float)
    percentage_error: Mapped[float] = mapped_column(Float)
    forecast_bias: Mapped[float] = mapped_column(Float, default=0)
    event_impacted: Mapped[bool] = mapped_column(Boolean, default=False)
    model_name: Mapped[str] = mapped_column(String(40), default="Legacy", index=True)
    horizon_minutes: Mapped[int] = mapped_column(Integer, default=0, index=True)
    cpu_squared_error: Mapped[float] = mapped_column(Float, default=0)
    ram_squared_error: Mapped[float] = mapped_column(Float, default=0)
    cpu_percentage_error: Mapped[float] = mapped_column(Float, default=0)
    ram_percentage_error: Mapped[float] = mapped_column(Float, default=0)
    failure_attribution: Mapped[str] = mapped_column(String(80), default="Normal forecast error", index=True)
    training_insufficient: Mapped[bool] = mapped_column(Boolean, default=False)
    successful: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    prediction: Mapped[Prediction] = relationship()
    provider: Mapped[Provider] = relationship()


class SimulationRun(Base):
    __tablename__ = "simulation_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    seed: Mapped[int] = mapped_column(Integer, index=True)
    scenario: Mapped[str] = mapped_column(String(32), index=True)
    random_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    forecast_model: Mapped[str] = mapped_column(String(40), default="Auto", index=True)
    shadow_models: Mapped[list[str]] = mapped_column(JSON, default=list)
    training_window_minutes: Mapped[int] = mapped_column(Integer, default=360)
    bartering_strategy: Mapped[str] = mapped_column(String(48), default="Confidence-Aware Predictive", index=True)
    safety_margin_multiplier: Mapped[float] = mapped_column(Float, default=1.0)
    model_selection_period_minutes: Mapped[int] = mapped_column(Integer, default=60)
    status: Mapped[str] = mapped_column(String(24), default="Ready", index=True)
    starting_time: Mapped[datetime] = mapped_column(DateTime)
    ending_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    simulation_duration_minutes: Mapped[float] = mapped_column(Float, default=0)
    configuration: Mapped[dict] = mapped_column(JSON, default=dict)
    final_statistics: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class StochasticEvent(Base):
    __tablename__ = "stochastic_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("simulation_runs.id", ondelete="CASCADE"), index=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    name: Mapped[str] = mapped_column(String(120))
    affected_resource: Mapped[str] = mapped_column(String(20), default="Both")
    start_time: Mapped[datetime] = mapped_column(DateTime, index=True)
    end_time: Mapped[datetime] = mapped_column(DateTime, index=True)
    magnitude_percent: Mapped[float] = mapped_column(Float)
    capacity_loss_percent: Mapped[float] = mapped_column(Float, default=0)
    severity: Mapped[str] = mapped_column(String(20), default="warning")
    source: Mapped[str] = mapped_column(String(24), default="automatic")
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    provider: Mapped[Provider] = relationship()


class ShortageEvent(Base):
    __tablename__ = "shortage_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("simulation_runs.id", ondelete="CASCADE"), index=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id", ondelete="CASCADE"), index=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    cpu_deficit: Mapped[float] = mapped_column(Float, default=0)
    ram_deficit: Mapped[float] = mapped_column(Float, default=0)
    resolution_type: Mapped[str] = mapped_column(String(24), default="Unresolved", index=True)
    outcome: Mapped[str] = mapped_column(String(40), default="Open", index=True)
    contract_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reaction_time_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)

    provider: Mapped[Provider] = relationship()


class SimulationState(Base):
    __tablename__ = "simulation_state"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    current_run_id: Mapped[int | None] = mapped_column(ForeignKey("simulation_runs.id"), nullable=True, index=True)
    current_time: Mapped[datetime] = mapped_column(DateTime, index=True)
    running: Mapped[bool] = mapped_column(Boolean, default=False)
    speed: Mapped[int] = mapped_column(Integer, default=25)
    seed: Mapped[int] = mapped_column(Integer, default=4281)
    scenario: Mapped[str] = mapped_column(String(32), default="Normal")
    random_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    configuration: Mapped[dict] = mapped_column(JSON, default=dict)
    forecast_model: Mapped[str] = mapped_column(String(40), default="Auto")
    shadow_models: Mapped[list[str]] = mapped_column(JSON, default=list)
    training_window_minutes: Mapped[int] = mapped_column(Integer, default=360)
    bartering_strategy: Mapped[str] = mapped_column(String(48), default="Confidence-Aware Predictive")
    safety_margin_multiplier: Mapped[float] = mapped_column(Float, default=1.0)
    model_selection_period_minutes: Mapped[int] = mapped_column(Integer, default=60)
    model_assignments: Mapped[dict] = mapped_column(JSON, default=dict)
    last_model_selection_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_real_tick: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_sample_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_prediction_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
