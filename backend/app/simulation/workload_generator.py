from datetime import datetime

from sqlalchemy.orm import Session

from ..models import Provider, ResourceState
from .clock import simulation_epoch
from .workload_profiles import workload_at


DEMO_PROVIDERS = [
    {"name": "Cloud A", "total_cpu": 80, "total_ram": 160, "credit_balance": 180, "sla_reputation": 94, "forecast_reliability": 89, "contribution_score": 72, "cpu_usage": 58, "ram_usage": 108},
    {"name": "Cloud B", "total_cpu": 100, "total_ram": 256, "credit_balance": 220, "sla_reputation": 96, "forecast_reliability": 91, "contribution_score": 88, "cpu_usage": 40, "ram_usage": 92},
    {"name": "Cloud C", "total_cpu": 120, "total_ram": 192, "credit_balance": 205, "sla_reputation": 91, "forecast_reliability": 86, "contribution_score": 76, "cpu_usage": 62, "ram_usage": 84},
    {"name": "Cloud D", "total_cpu": 90, "total_ram": 128, "credit_balance": 150, "sla_reputation": 87, "forecast_reliability": 78, "contribution_score": 61, "cpu_usage": 65, "ram_usage": 101},
]


def seed_provider_workloads(db: Session) -> list[Provider]:
    providers: list[Provider] = []
    for item in DEMO_PROVIDERS:
        provider = Provider(**{key: value for key, value in item.items() if key not in {"cpu_usage", "ram_usage"}})
        db.add(provider)
        db.flush()
        simulated = workload_at(provider.name, simulation_epoch())
        db.add(
            ResourceState(
                provider_id=provider.id,
                cpu_usage=simulated.cpu,
                ram_usage=simulated.ram,
                cpu_available=max(provider.total_cpu - simulated.cpu, 0),
                ram_available=max(provider.total_ram - simulated.ram, 0),
                effective_future_cpu=max(provider.total_cpu - simulated.cpu, 0),
                effective_future_ram=max(provider.total_ram - simulated.ram, 0),
                simulation_time=simulation_epoch(),
                observed_at=datetime.utcnow(),
                source="seeded simulation",
            )
        )
        providers.append(provider)
    db.flush()
    return providers
