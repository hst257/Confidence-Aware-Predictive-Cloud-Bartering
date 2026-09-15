from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import ContractStatus, Prediction, Provider, ResourceState, SimulationState


@dataclass
class MatchCandidate:
    provider_id: int
    provider_name: str
    consumer_id: int
    consumer_name: str
    prediction_id: int
    demand_prediction_id: int
    horizon_minutes: int
    cpu_amount: float
    ram_amount: float
    requested_cpu: float
    requested_ram: float
    window_start: object
    window_end: object
    confidence: float
    forecast_reliability: float
    sla_reputation: float
    match_score: float
    barter_cost: float
    collateral: float
    safe_cpu_available: float
    safe_ram_available: float
    reserved_cpu: float
    reserved_ram: float
    contribution_score: float
    selection_reason: str

    def as_dict(self) -> dict:
        return self.__dict__


def resource_cost(cpu: float, ram: float) -> float:
    settings = get_settings()
    return round(cpu * settings.cpu_credit_rate + ram * settings.ram_credit_rate, 2)


def collateral_cost(barter_cost: float) -> float:
    return round(barter_cost * get_settings().collateral_rate, 2)


def _committed(db: Session, provider_id: int, prediction: Prediction) -> tuple[float, float]:
    from ..models import BarterContract

    contracts = db.scalars(
        select(BarterContract).where(
            BarterContract.provider_id == provider_id,
            BarterContract.run_id == prediction.run_id,
            BarterContract.status.in_([ContractStatus.PROPOSED, ContractStatus.SCHEDULED, ContractStatus.AT_RISK, ContractStatus.ACTIVE]),
            BarterContract.start_time < prediction.window_end,
            BarterContract.end_time > prediction.window_start,
        )
    ).all()
    return sum(item.cpu_amount for item in contracts), sum(item.ram_amount for item in contracts)


def find_matches(
    db: Session,
    *,
    excluded_provider_ids: set[int] | None = None,
    cycle_id: str | None = None,
) -> list[MatchCandidate]:
    settings = get_settings()
    state = db.get(SimulationState, 1)
    if not state or not state.current_run_id:
        return []
    excluded_provider_ids = excluded_provider_ids or set()
    query = select(Prediction).where(
        Prediction.run_id == state.current_run_id,
        Prediction.superseded.is_(False),
    ).order_by(Prediction.window_start, Prediction.id)
    if cycle_id is not None:
        query = query.where(Prediction.cycle_id == cycle_id)
    predictions = db.scalars(query).all()
    provider_map = {provider.id: provider for provider in db.scalars(select(Provider)).all()}
    deficits = [p for p in predictions if p.cpu_deficit > 0 or p.ram_deficit > 0]
    surpluses = [p for p in predictions if p.predicted_cpu_spare > 0 or p.predicted_ram_spare > 0]
    matches: list[MatchCandidate] = []
    for demand in deficits:
        consumer = provider_map[demand.provider_id]
        for supply in surpluses:
            if supply.provider_id in excluded_provider_ids or supply.provider_id == consumer.id:
                continue
            if supply.window_start >= demand.window_end or supply.window_end <= demand.window_start:
                continue
            if cycle_id is not None and supply.window_start != demand.window_start:
                continue
            provider = provider_map[supply.provider_id]
            committed_cpu, committed_ram = _committed(db, provider.id, supply)
            available_cpu = max(0.0, supply.safe_cpu_commitment - committed_cpu)
            available_ram = max(0.0, supply.safe_ram_commitment - committed_ram)
            current = db.scalar(select(ResourceState).where(
                ResourceState.run_id == state.current_run_id,
                ResourceState.provider_id == provider.id,
            ).order_by(ResourceState.simulation_time.desc(), ResourceState.id.desc()))
            if current and current.cpu_capacity_lost > 0:
                available_cpu = min(available_cpu, current.effective_future_cpu)
            if current and current.ram_capacity_lost > 0:
                available_ram = min(available_ram, current.effective_future_ram)
            cpu = min(demand.cpu_deficit, available_cpu)
            ram = min(demand.ram_deficit, available_ram)
            if (demand.cpu_deficit > 0 and cpu <= 0) or (demand.ram_deficit > 0 and ram <= 0):
                continue
            cpu_fit = 1 if demand.cpu_deficit == 0 else cpu / demand.cpu_deficit
            ram_fit = 1 if demand.ram_deficit == 0 else ram / demand.ram_deficit
            capacity_fit = (cpu_fit + ram_fit) / 2
            score = 100 * (
                settings.confidence_weight * supply.confidence / 100
                + settings.reliability_weight * provider.forecast_reliability / 100
                + settings.sla_weight * provider.sla_reputation / 100
                + settings.capacity_weight * capacity_fit
                + settings.contribution_weight * min(provider.contribution_score / 100, 1)
                + settings.credit_balance_weight * min(provider.credit_balance / 250, 1)
            )
            cost = resource_cost(cpu, ram)
            if consumer.credit_balance < cost:
                continue
            score = round(score, 1)
            reason = (
                f"Covers {capacity_fit * 100:.0f}% of this deficit; {supply.confidence:.0f}% forecast confidence, "
                f"{provider.forecast_reliability:.0f}% forecast reliability, {provider.sla_reputation:.0f}% SLA reputation, "
                f"{available_cpu:.1f} safe CPU after {committed_cpu:.1f} reserved, and a {provider.contribution_score:.0f} contribution score."
            )
            matches.append(
                MatchCandidate(
                    provider_id=provider.id,
                    provider_name=provider.name,
                    consumer_id=consumer.id,
                    consumer_name=consumer.name,
                    prediction_id=supply.id,
                    demand_prediction_id=demand.id,
                    horizon_minutes=demand.horizon_minutes,
                    cpu_amount=round(cpu, 2),
                    ram_amount=round(ram, 2),
                    requested_cpu=demand.cpu_deficit,
                    requested_ram=demand.ram_deficit,
                    window_start=demand.window_start,
                    window_end=demand.window_end,
                    confidence=supply.confidence,
                    forecast_reliability=provider.forecast_reliability,
                    sla_reputation=provider.sla_reputation,
                    match_score=score,
                    barter_cost=cost,
                    collateral=collateral_cost(cost),
                    safe_cpu_available=round(available_cpu, 2),
                    safe_ram_available=round(available_ram, 2),
                    reserved_cpu=round(committed_cpu, 2),
                    reserved_ram=round(committed_ram, 2),
                    contribution_score=provider.contribution_score,
                    selection_reason=reason,
                )
            )
    return sorted(matches, key=lambda item: (-item.match_score, item.provider_name))
