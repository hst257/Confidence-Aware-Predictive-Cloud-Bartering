from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import BarterContract, ReputationHistory
from .event_service import record_event


def _accuracy(predicted: float, actual: float) -> float:
    baseline = max(abs(predicted), 1.0)
    return round(max(0.0, 100.0 * (1.0 - abs(predicted - actual) / baseline)), 2)


def settle_reputation(
    db: Session,
    contract: BarterContract,
    actual_cpu: float,
    actual_ram: float,
    simulation_time=None,
) -> float:
    settings = get_settings()
    provider = contract.provider
    prediction = contract.prediction
    predicted_cpu = prediction.predicted_cpu_spare if prediction else contract.cpu_amount
    predicted_ram = prediction.predicted_ram_spare if prediction else contract.ram_amount
    cpu_accuracy = _accuracy(predicted_cpu, actual_cpu)
    ram_accuracy = _accuracy(predicted_ram, actual_ram)
    accuracy = round((cpu_accuracy + ram_accuracy) / 2, 2)

    old_reliability = provider.forecast_reliability
    provider.forecast_reliability = round(
        old_reliability * (1 - settings.reputation_learning_rate) + accuracy * settings.reputation_learning_rate,
        2,
    )
    db.add(
        ReputationHistory(
            run_id=contract.run_id,
            provider_id=provider.id,
            contract_id=contract.id,
            metric="Forecast reliability",
            old_value=old_reliability,
            new_value=provider.forecast_reliability,
            forecast_accuracy=accuracy,
            reason="Predicted spare capacity compared with simulated actual spare capacity",
            simulation_time=simulation_time,
        )
    )

    old_sla = provider.sla_reputation
    provider.sla_reputation = round(min(100.0, old_sla + settings.success_sla_bonus), 2)
    db.add(
        ReputationHistory(
            run_id=contract.run_id,
            provider_id=provider.id,
            contract_id=contract.id,
            metric="SLA reputation",
            old_value=old_sla,
            new_value=provider.sla_reputation,
            forecast_accuracy=accuracy,
            reason="Contract completed successfully",
            simulation_time=simulation_time,
        )
    )
    provider.successful_contracts += 1
    provider.contribution_score = round(provider.contribution_score + contract.cpu_amount + contract.ram_amount * 0.25, 2)
    record_event(
        db,
        "reputation.updated",
        f"{provider.name} forecast accuracy was {accuracy:g}%; reliability is now {provider.forecast_reliability:g}",
        provider_id=provider.id,
        contract_id=contract.id,
        details={"accuracy": accuracy, "reliability": provider.forecast_reliability},
        simulation_time=simulation_time,
    )
    return accuracy


def record_failure(db: Session, contract: BarterContract, simulation_time=None) -> None:
    settings = get_settings()
    provider = contract.provider
    old_reliability = provider.forecast_reliability
    provider.forecast_reliability = round(max(0.0, old_reliability - settings.failure_reliability_penalty), 2)
    provider.failed_predictions += 1
    db.add(
        ReputationHistory(
            run_id=contract.run_id,
            provider_id=provider.id,
            contract_id=contract.id,
            metric="Forecast reliability",
            old_value=old_reliability,
            new_value=provider.forecast_reliability,
            forecast_accuracy=0,
            reason="Promised future capacity was not delivered",
            simulation_time=simulation_time,
        )
    )
    old_sla = provider.sla_reputation
    provider.sla_reputation = round(max(0.0, old_sla - settings.failure_sla_penalty), 2)
    db.add(
        ReputationHistory(
            run_id=contract.run_id,
            provider_id=provider.id,
            contract_id=contract.id,
            metric="SLA reputation",
            old_value=old_sla,
            new_value=provider.sla_reputation,
            forecast_accuracy=0,
            reason="Contract failed",
            simulation_time=simulation_time,
        )
    )
    record_event(
        db,
        "reputation.penalized",
        f"{provider.name} reliability fell to {provider.forecast_reliability:g} after a failed commitment",
        severity="error",
        provider_id=provider.id,
        contract_id=contract.id,
        simulation_time=simulation_time,
    )
