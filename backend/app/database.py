from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


database_url = get_settings().database_url
engine_options = {"connect_args": {"check_same_thread": False}} if database_url.startswith("sqlite") else {}
engine = create_engine(database_url, pool_pre_ping=True, **engine_options)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_database() -> None:
    # Import registers every mapped class before metadata creation.
    from . import models  # noqa: F401

    _upgrade_prototype_schema()
    Base.metadata.create_all(bind=engine)


def _upgrade_prototype_schema() -> None:
    """Additive migration for existing Phase 1/2 prototype installations.

    Phase 3 adds only nullable/defaulted columns here; new stochastic-run tables
    are created by metadata afterward, preserving all earlier prototype data.
    """
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if not tables:
        return

    dialect = engine.dialect.name
    real_type = "DOUBLE PRECISION" if dialect == "postgresql" else "REAL"
    timestamp_type = "TIMESTAMP"
    additions: dict[str, dict[str, str]] = {
        "resource_states": {
            "run_id": "INTEGER",
            "cpu_available": f"{real_type} NOT NULL DEFAULT 0",
            "ram_available": f"{real_type} NOT NULL DEFAULT 0",
            "reserved_future_cpu": f"{real_type} NOT NULL DEFAULT 0",
            "reserved_future_ram": f"{real_type} NOT NULL DEFAULT 0",
            "effective_future_cpu": f"{real_type} NOT NULL DEFAULT 0",
            "effective_future_ram": f"{real_type} NOT NULL DEFAULT 0",
            "simulation_time": timestamp_type,
            "baseline_cpu": f"{real_type} NOT NULL DEFAULT 0",
            "baseline_ram": f"{real_type} NOT NULL DEFAULT 0",
            "usable_cpu": f"{real_type} NOT NULL DEFAULT 0",
            "usable_ram": f"{real_type} NOT NULL DEFAULT 0",
            "cpu_capacity_lost": f"{real_type} NOT NULL DEFAULT 0",
            "ram_capacity_lost": f"{real_type} NOT NULL DEFAULT 0",
            "random_noise_cpu": f"{real_type} NOT NULL DEFAULT 0",
            "random_noise_ram": f"{real_type} NOT NULL DEFAULT 0",
            "volatility": f"{real_type} NOT NULL DEFAULT 0",
        },
        "predictions": {
            "run_id": "INTEGER",
            "simulation_generated_at": timestamp_type,
            "horizon_minutes": "INTEGER NOT NULL DEFAULT 0",
            "cycle_id": "VARCHAR(64)",
            "recent_volatility": f"{real_type} NOT NULL DEFAULT 0",
            "model_name": "VARCHAR(40) NOT NULL DEFAULT 'Legacy'",
            "decision_forecast": "BOOLEAN NOT NULL DEFAULT TRUE",
            "uncertainty_cpu": f"{real_type} NOT NULL DEFAULT 0",
            "uncertainty_ram": f"{real_type} NOT NULL DEFAULT 0",
            "fallback_model": "VARCHAR(40)",
            "training_points": "INTEGER NOT NULL DEFAULT 0",
            "training_window_minutes": "INTEGER NOT NULL DEFAULT 0",
            "revision_number": "INTEGER NOT NULL DEFAULT 1",
            "model_metadata": "JSON",
        },
        "barter_contracts": {
            "run_id": "INTEGER",
            "created_simulation_time": timestamp_type,
            "barter_type": "VARCHAR(24) NOT NULL DEFAULT 'Predictive'",
            "emergency_reason": "VARCHAR(240)",
            "reaction_time_minutes": real_type,
        },
        "credit_transactions": {"run_id": "INTEGER", "simulation_time": timestamp_type},
        "collaterals": {"run_id": "INTEGER"},
        "reputation_history": {"run_id": "INTEGER", "simulation_time": timestamp_type},
        "renegotiation_events": {"run_id": "INTEGER", "simulation_time": timestamp_type},
        "event_logs": {"run_id": "INTEGER", "simulation_time": timestamp_type},
        "prediction_evaluations": {
            "run_id": "INTEGER",
            "forecast_bias": f"{real_type} NOT NULL DEFAULT 0",
            "event_impacted": "BOOLEAN NOT NULL DEFAULT FALSE",
            "model_name": "VARCHAR(40) NOT NULL DEFAULT 'Legacy'",
            "horizon_minutes": "INTEGER NOT NULL DEFAULT 0",
            "cpu_squared_error": f"{real_type} NOT NULL DEFAULT 0",
            "ram_squared_error": f"{real_type} NOT NULL DEFAULT 0",
            "cpu_percentage_error": f"{real_type} NOT NULL DEFAULT 0",
            "ram_percentage_error": f"{real_type} NOT NULL DEFAULT 0",
            "failure_attribution": "VARCHAR(80) NOT NULL DEFAULT 'Normal forecast error'",
            "training_insufficient": "BOOLEAN NOT NULL DEFAULT FALSE",
        },
        "simulation_state": {
            "current_run_id": "INTEGER",
            "seed": "INTEGER NOT NULL DEFAULT 4281",
            "scenario": "VARCHAR(32) NOT NULL DEFAULT 'Normal'",
            "random_mode": "BOOLEAN NOT NULL DEFAULT FALSE",
            "configuration": "JSON",
            "forecast_model": "VARCHAR(40) NOT NULL DEFAULT 'Auto'",
            "shadow_models": "JSON",
            "training_window_minutes": "INTEGER NOT NULL DEFAULT 360",
            "bartering_strategy": "VARCHAR(48) NOT NULL DEFAULT 'Confidence-Aware Predictive'",
            "safety_margin_multiplier": f"{real_type} NOT NULL DEFAULT 1",
            "model_selection_period_minutes": "INTEGER NOT NULL DEFAULT 60",
            "model_assignments": "JSON",
            "last_model_selection_at": timestamp_type,
        },
        "simulation_runs": {
            "forecast_model": "VARCHAR(40) NOT NULL DEFAULT 'Auto'",
            "shadow_models": "JSON",
            "training_window_minutes": "INTEGER NOT NULL DEFAULT 360",
            "bartering_strategy": "VARCHAR(48) NOT NULL DEFAULT 'Confidence-Aware Predictive'",
            "safety_margin_multiplier": f"{real_type} NOT NULL DEFAULT 1",
            "model_selection_period_minutes": "INTEGER NOT NULL DEFAULT 60",
        },
    }
    with engine.begin() as connection:
        if dialect == "postgresql" and "barter_contracts" in tables:
            connection.exec_driver_sql("ALTER TYPE contractstatus ADD VALUE IF NOT EXISTS 'AT_RISK'")
        for table, columns in additions.items():
            if table not in tables:
                continue
            existing = {column["name"] for column in inspect(connection).get_columns(table)}
            for name, sql_type in columns.items():
                if name not in existing:
                    connection.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}")
        if "predictions" in tables:
            connection.exec_driver_sql("UPDATE predictions SET model_metadata = '{}' WHERE model_metadata IS NULL")
