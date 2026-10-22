from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Provider


DEMO_PROVIDERS = [
    {"name": "Cloud A", "total_cpu": 80, "total_ram": 160, "credit_balance": 180, "sla_reputation": 94, "forecast_reliability": 89, "contribution_score": 72, "cpu_usage": 58, "ram_usage": 108},
    {"name": "Cloud B", "total_cpu": 100, "total_ram": 256, "credit_balance": 220, "sla_reputation": 96, "forecast_reliability": 91, "contribution_score": 88, "cpu_usage": 40, "ram_usage": 92},
    {"name": "Cloud C", "total_cpu": 120, "total_ram": 192, "credit_balance": 205, "sla_reputation": 91, "forecast_reliability": 86, "contribution_score": 76, "cpu_usage": 62, "ram_usage": 84},
    {"name": "Cloud D", "total_cpu": 90, "total_ram": 128, "credit_balance": 150, "sla_reputation": 87, "forecast_reliability": 78, "contribution_score": 61, "cpu_usage": 65, "ram_usage": 101},
    {"name": "Cloud E", "total_cpu": 112, "total_ram": 224, "credit_balance": 195, "sla_reputation": 93, "forecast_reliability": 88, "contribution_score": 74, "cpu_usage": 58, "ram_usage": 132},
    {"name": "Cloud F", "total_cpu": 144, "total_ram": 288, "credit_balance": 235, "sla_reputation": 95, "forecast_reliability": 90, "contribution_score": 82, "cpu_usage": 76, "ram_usage": 151},
    {"name": "Cloud G", "total_cpu": 72, "total_ram": 144, "credit_balance": 165, "sla_reputation": 89, "forecast_reliability": 83, "contribution_score": 67, "cpu_usage": 36, "ram_usage": 72},
    {"name": "Cloud H", "total_cpu": 128, "total_ram": 320, "credit_balance": 215, "sla_reputation": 92, "forecast_reliability": 87, "contribution_score": 79, "cpu_usage": 64, "ram_usage": 186},
    {"name": "Cloud I", "total_cpu": 96, "total_ram": 192, "credit_balance": 175, "sla_reputation": 90, "forecast_reliability": 85, "contribution_score": 70, "cpu_usage": 45, "ram_usage": 94},
    {"name": "Cloud J", "total_cpu": 160, "total_ram": 256, "credit_balance": 245, "sla_reputation": 94, "forecast_reliability": 89, "contribution_score": 84, "cpu_usage": 88, "ram_usage": 136},
]


def seed_provider_workloads(db: Session) -> list[Provider]:
    """Add missing federation members without changing existing provider state.

    The run service initializes observations after choosing the current clock.
    This also makes expansion safe for databases seeded by earlier versions.
    """
    providers = list(db.scalars(select(Provider).order_by(Provider.id)).all())
    existing_names = {provider.name for provider in providers}
    for item in DEMO_PROVIDERS:
        if item["name"] in existing_names:
            continue
        provider = Provider(**{key: value for key, value in item.items() if key not in {"cpu_usage", "ram_usage"}})
        db.add(provider)
        db.flush()
        providers.append(provider)
        existing_names.add(provider.name)
    db.flush()
    return providers
