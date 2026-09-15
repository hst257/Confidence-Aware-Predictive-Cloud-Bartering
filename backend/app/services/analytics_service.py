from datetime import timedelta
from math import sqrt

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import (
    BarterContract,
    Collateral,
    CollateralStatus,
    ContractStatus,
    CreditTransaction,
    CreditTransactionType,
    Prediction,
    PredictionEvaluation,
    Provider,
    ReputationHistory,
    ResourceState,
    ShortageEvent,
    SimulationState,
    StochasticEvent,
)
from ..simulation.simulation_state import get_or_create_state
from ..forecasting.confidence import CONFIDENCE_FORMULA
from ..forecasting.model_manager import AVAILABLE_MODELS


def _current_run_id(db: Session, run_id: int | None = None) -> int | None:
    return run_id if run_id is not None else get_or_create_state(db).current_run_id


def provider_forecast_metrics(db: Session, run_id: int | None = None) -> list[dict]:
    selected_run = _current_run_id(db, run_id)
    result = []
    for provider in db.scalars(select(Provider).order_by(Provider.id)).all():
        evaluations = db.scalars(select(PredictionEvaluation).where(
            PredictionEvaluation.run_id == selected_run,
            PredictionEvaluation.provider_id == provider.id,
        )).all()
        predictions = db.scalars(select(Prediction).where(
            Prediction.run_id == selected_run,
            Prediction.provider_id == provider.id,
            Prediction.simulation_generated_at.is_not(None),
        )).all()
        evaluated = len(evaluations)
        successful = sum(item.successful for item in evaluations)
        result.append({
            "provider_id": provider.id,
            "provider_name": provider.name,
            "cpu_mae": round(sum(item.cpu_absolute_error for item in evaluations) / evaluated, 2) if evaluated else 0,
            "ram_mae": round(sum(item.ram_absolute_error for item in evaluations) / evaluated, 2) if evaluated else 0,
            "percentage_error": round(sum(item.percentage_error for item in evaluations) / evaluated, 2) if evaluated else 0,
            "forecast_bias": round(sum(item.forecast_bias for item in evaluations) / evaluated, 2) if evaluated else 0,
            "average_confidence": round(sum(item.confidence for item in predictions) / len(predictions), 2) if predictions else 0,
            "predictions_evaluated": evaluated,
            "successful_forecasts": successful,
            "failed_forecasts": evaluated - successful,
            "event_impacted_forecasts": sum(item.event_impacted for item in evaluations),
            "success_rate": round(successful / evaluated * 100, 2) if evaluated else 0,
        })
    return result


def confidence_calibration(db: Session, run_id: int | None = None) -> list[dict]:
    selected_run = _current_run_id(db, run_id)
    rows = db.execute(select(PredictionEvaluation, Prediction).join(
        Prediction, Prediction.id == PredictionEvaluation.prediction_id,
    ).where(PredictionEvaluation.run_id == selected_run)).all()
    buckets = [(50, 60), (60, 70), (70, 80), (80, 90), (90, 100)]
    result = []
    for low, high in buckets:
        items = [(evaluation, prediction) for evaluation, prediction in rows if low <= prediction.confidence < high or (high == 100 and prediction.confidence == 100)]
        count = len(items)
        result.append({
            "bucket": f"{low}–{high}%",
            "prediction_count": count,
            "average_confidence": round(sum(prediction.confidence for _, prediction in items) / count, 2) if count else 0,
            "success_rate": round(sum(evaluation.successful for evaluation, _ in items) / count * 100, 2) if count else 0,
            "average_error": round(sum(evaluation.percentage_error for evaluation, _ in items) / count, 2) if count else 0,
        })
    return result


def forecasting_analytics(db: Session, run_id: int | None = None) -> dict:
    selected_run = _current_run_id(db, run_id)
    providers = {item.id: item.name for item in db.scalars(select(Provider)).all()}
    predictions = db.scalars(select(Prediction).where(
        Prediction.run_id == selected_run,
        Prediction.simulation_generated_at.is_not(None),
    ).order_by(Prediction.simulation_generated_at, Prediction.id)).all()
    evaluations = db.scalars(select(PredictionEvaluation).where(
        PredictionEvaluation.run_id == selected_run,
    ).order_by(PredictionEvaluation.simulation_time, PredictionEvaluation.id)).all()
    prediction_map = {item.id: item for item in predictions}
    contracts = db.scalars(select(BarterContract).where(BarterContract.run_id == selected_run)).all()

    def metrics(items: list[PredictionEvaluation]) -> dict:
        count = len(items)
        if not count:
            return {"evaluations": 0, "cpu_mae": 0, "ram_mae": 0, "rmse": 0, "mape": 0, "bias": 0, "success_rate": 0}
        return {
            "evaluations": count,
            "cpu_mae": round(sum(x.cpu_absolute_error for x in items) / count, 3),
            "ram_mae": round(sum(x.ram_absolute_error for x in items) / count, 3),
            "rmse": round(sqrt(sum(x.cpu_squared_error + x.ram_squared_error for x in items) / (2 * count)), 3),
            "mape": round(sum(x.percentage_error for x in items) / count, 3),
            "bias": round(sum(x.forecast_bias for x in items) / count, 3),
            "success_rate": round(sum(x.successful for x in items) / count * 100, 2),
        }

    model_rows = []
    for model_name in AVAILABLE_MODELS:
        model_evals = [x for x in evaluations if x.model_name == model_name]
        model_predictions = [x for x in predictions if x.model_name == model_name]
        ids = {x.id for x in model_predictions}
        model_contracts = [x for x in contracts if x.prediction_id in ids]
        settled_model_contracts = [x for x in model_contracts if x.status in {ContractStatus.COMPLETED, ContractStatus.FAILED}]
        row = metrics(model_evals)
        row.update({
            "model_name": model_name,
            "average_confidence": round(sum(x.confidence for x in model_predictions) / len(model_predictions), 2) if model_predictions else 0,
            "forecast_count": len(model_predictions),
            "decision_forecasts": sum(x.decision_forecast for x in model_predictions),
            "fallbacks": sum(x.fallback_model is not None for x in model_predictions),
            "contracts": len(model_contracts),
            "sla_failures": sum(x.status == ContractStatus.FAILED for x in model_contracts),
            "model_contract_success_rate": round(sum(x.status == ContractStatus.COMPLETED for x in settled_model_contracts) / len(settled_model_contracts) * 100, 2) if settled_model_contracts else 0,
        })
        model_rows.append(row)

    horizon_rows = []
    for model_name in AVAILABLE_MODELS:
        for horizon in get_settings().prediction_horizons:
            items = [x for x in evaluations if x.model_name == model_name and x.horizon_minutes == horizon]
            row = metrics(items)
            row.update({"model_name": model_name, "horizon_minutes": horizon})
            horizon_rows.append(row)

    error_timeline = []
    for item in evaluations[-1200:]:
        prediction = prediction_map.get(item.prediction_id)
        error_timeline.append({
            "time": item.simulation_time.isoformat(), "provider_id": item.provider_id,
            "provider_name": providers.get(item.provider_id, "Unknown"), "model_name": item.model_name,
            "horizon_minutes": item.horizon_minutes, "cpu_error": item.cpu_absolute_error,
            "ram_error": item.ram_absolute_error, "percentage_error": item.percentage_error,
            "bias": item.forecast_bias, "successful": item.successful,
            "confidence": prediction.confidence if prediction else 0,
            "failure_attribution": item.failure_attribution,
        })
    revision_tracks = [{
        "prediction_id": item.id, "provider_id": item.provider_id,
        "provider_name": providers.get(item.provider_id, "Unknown"), "model_name": item.model_name,
        "target_time": item.window_start.isoformat(),
        "generated_at": item.simulation_generated_at.isoformat() if item.simulation_generated_at else None,
        "horizon_minutes": item.horizon_minutes, "revision_number": item.revision_number,
        "predicted_cpu": item.predicted_cpu_usage, "predicted_ram": item.predicted_ram_usage,
        "uncertainty_cpu": item.uncertainty_cpu, "uncertainty_ram": item.uncertainty_ram,
        "confidence": item.confidence, "decision_forecast": item.decision_forecast,
        "fallback_model": item.fallback_model,
    } for item in predictions[-1600:]]
    return {
        "models": AVAILABLE_MODELS,
        "horizons": get_settings().prediction_horizons,
        "confidence_formula": CONFIDENCE_FORMULA,
        "model_metrics": model_rows,
        "horizon_metrics": horizon_rows,
        "error_timeline": error_timeline,
        "revision_tracks": revision_tracks,
        "calibration": confidence_calibration(db, selected_run),
    }


def analytics_summary(db: Session, run_id: int | None = None, include_runs: bool = True) -> dict:
    selected_run = _current_run_id(db, run_id)
    state = db.get(SimulationState, 1)
    providers = db.scalars(select(Provider).order_by(Provider.id)).all()
    contracts = db.scalars(select(BarterContract).where(BarterContract.run_id == selected_run)).all()
    evaluations = db.scalars(select(PredictionEvaluation).where(PredictionEvaluation.run_id == selected_run)).all()
    shortages = db.scalars(select(ShortageEvent).where(ShortageEvent.run_id == selected_run)).all()
    stochastic_events = db.scalars(select(StochasticEvent).where(StochasticEvent.run_id == selected_run)).all()
    current_states: list[tuple[Provider, ResourceState]] = []
    for provider in providers:
        current = db.scalar(select(ResourceState).where(
            ResourceState.run_id == selected_run,
            ResourceState.provider_id == provider.id,
        ).order_by(ResourceState.simulation_time.desc(), ResourceState.id.desc()))
        if current:
            current_states.append((provider, current))
    total_cpu = sum(state.usable_cpu for _, state in current_states)
    total_ram = sum(state.usable_ram for _, state in current_states)
    cpu_used = sum(resource.cpu_usage for _, resource in current_states)
    ram_used = sum(resource.ram_usage for _, resource in current_states)
    completed = [item for item in contracts if item.status == ContractStatus.COMPLETED]
    failed = [item for item in contracts if item.status == ContractStatus.FAILED]
    renegotiated = [item for item in contracts if item.status == ContractStatus.RENEGOTIATED]
    settled_count = len(completed) + len(failed)
    transactions = db.scalars(select(CreditTransaction).where(CreditTransaction.run_id == selected_run)).all()
    transferred = sum(item.amount for item in transactions if item.transaction_type == CreditTransactionType.CONTRACT_EARNING)
    penalties = sum(item.amount for item in db.scalars(select(Collateral).where(
        Collateral.run_id == selected_run, Collateral.status == CollateralStatus.FORFEITED,
    )).all())
    avg_accuracy = 100 - (sum(item.percentage_error for item in evaluations) / len(evaluations)) if evaluations else 0
    predictive_contracts = [item for item in contracts if item.barter_type == "Predictive"]
    emergency_contracts = [item for item in contracts if item.barter_type == "Emergency"]
    prevented = sum(item.resolution_type == "Predictive" and item.outcome == "Prevented" for item in shortages)
    emergency_recoveries = sum(item.resolution_type == "Emergency" and item.outcome == "Recovered" for item in shortages)
    unresolved = sum(item.outcome == "Unresolved" for item in shortages)
    shortage_total = len(shortages)
    resolution_rate = (prevented + emergency_recoveries) / shortage_total * 100 if shortage_total else 100
    renegotiation_success = len(renegotiated) / max(1, len(renegotiated) + len(failed)) * 100 if renegotiated or failed else 100
    average_sla = sum(provider.sla_reputation for provider in providers) / len(providers) if providers else 0
    completion_rate = len(completed) / settled_count * 100 if settled_count else 100
    resilience = round(0.40 * resolution_rate + 0.20 * renegotiation_success + 0.20 * average_sla + 0.20 * completion_rate, 2)
    cpu_hours = sum(item.cpu_amount * max(0, (item.end_time - item.start_time).total_seconds()) / 3600 for item in completed)
    ram_hours = sum(item.ram_amount * max(0, (item.end_time - item.start_time).total_seconds()) / 3600 for item in completed)
    event_now = state.current_time if state else None
    prediction_lead_times = [
        (item.start_time - item.created_simulation_time).total_seconds() / 60
        for item in predictive_contracts if item.created_simulation_time is not None
    ]
    active_events = [item for item in stochastic_events if event_now and item.start_time <= event_now < item.end_time]
    predictions = db.scalars(select(Prediction).where(
        Prediction.run_id == selected_run, Prediction.superseded.is_(False), Prediction.decision_forecast.is_(True),
    )).all()
    result = {
        "run_id": selected_run,
        "total_cpu_utilization": round(cpu_used / total_cpu * 100, 2) if total_cpu else 0,
        "total_ram_utilization": round(ram_used / total_ram * 100, 2) if total_ram else 0,
        "utilization_before_barter": round((cpu_used / total_cpu * 100), 2) if total_cpu else 0,
        "utilization_after_barter": round((cpu_used - sum(item.cpu_amount for item in completed)) / max(total_cpu, 1) * 100, 2),
        "resource_sharing_cpu": round(sum(item.cpu_amount for item in completed), 2),
        "resource_sharing_ram": round(sum(item.ram_amount for item in completed), 2),
        "cpu_hours_exchanged": round(cpu_hours, 2),
        "ram_hours_exchanged": round(ram_hours, 2),
        "idle_capacity_shared": round(sum(item.cpu_amount + item.ram_amount for item in completed), 2),
        "providers_helped": len({item.consumer_id for item in completed}),
        "shortages_avoided": prevented,
        "shortages_prevented": prevented,
        "emergency_recoveries": emergency_recoveries,
        "unresolved_shortages": unresolved,
        "barter_transactions": len(contracts),
        "predictive_contracts": len(predictive_contracts),
        "emergency_contracts": len(emergency_contracts),
        "average_prediction_lead_time": round(sum(prediction_lead_times) / len(prediction_lead_times), 2) if prediction_lead_times else 0,
        "renegotiations": len(renegotiated),
        "failed_contracts": len(failed),
        "average_reaction_time": round(sum(item.reaction_time_minutes or 0 for item in shortages if item.resolution_type == "Emergency") / max(1, emergency_recoveries), 2),
        "credit_circulation": round(transferred, 2),
        "average_forecast_accuracy": round(max(0, avg_accuracy), 2),
        "contract_success_rate": round(len(completed) / settled_count * 100, 2) if settled_count else 0,
        "renegotiation_rate": round(len(renegotiated) / len(contracts) * 100, 2) if contracts else 0,
        "failure_recovery_rate": round(sum(not item.active for item in stochastic_events if item.event_type == "capacity_failure") / max(1, sum(item.event_type == "capacity_failure" for item in stochastic_events)) * 100, 2),
        "system_resilience_score": resilience,
        "resilience_formula": "40% shortage resolution + 20% renegotiation success + 20% mean SLA + 20% contract completion (project-specific simulation metric)",
        "active_events": len(active_events),
        "active_failures": sum(item.event_type == "capacity_failure" for item in active_events),
        "current_emergencies": sum(item.status == ContractStatus.ACTIVE and item.barter_type == "Emergency" for item in contracts),
        "active_contracts": sum(item.status == ContractStatus.ACTIVE for item in contracts),
        "at_risk_contracts": sum(item.status == ContractStatus.AT_RISK for item in contracts),
        "predicted_deficits": sum(item.cpu_deficit > 0 or item.ram_deficit > 0 for item in predictions),
        "contract_counts": {status.value: sum(item.status == status for item in contracts) for status in ContractStatus},
        "collateral_penalties": round(penalties, 2),
        "providers": [{
            "id": provider.id, "name": provider.name,
            "cpu_utilization": round(resource.cpu_usage / max(resource.usable_cpu, 1) * 100, 2),
            "ram_utilization": round(resource.ram_usage / max(resource.usable_ram, 1) * 100, 2),
            "credits": provider.credit_balance, "sla_reputation": provider.sla_reputation,
            "forecast_reliability": provider.forecast_reliability, "volatility": resource.volatility,
        } for provider, resource in current_states],
        "forecast_metrics": provider_forecast_metrics(db, selected_run),
        "confidence_calibration": confidence_calibration(db, selected_run),
        "strategy": state.bartering_strategy if state and state.current_run_id == selected_run else None,
    }
    if include_runs:
        from ..simulation.run_service import list_run_summaries

        result["runs"] = list_run_summaries(db)
    return result


def provider_analytics(db: Session, provider_id: int, range_minutes: int = 360) -> dict | None:
    provider = db.get(Provider, provider_id)
    if not provider:
        return None
    state = get_or_create_state(db)
    run_id = state.current_run_id
    since = state.current_time - timedelta(minutes=range_minutes)
    limit = get_settings().max_history_points
    resource_history = db.scalars(select(ResourceState).where(
        ResourceState.run_id == run_id, ResourceState.provider_id == provider_id,
        ResourceState.simulation_time >= since,
    ).order_by(ResourceState.simulation_time.desc()).limit(limit)).all()[::-1]
    predictions = db.scalars(select(Prediction).where(
        Prediction.run_id == run_id, Prediction.provider_id == provider_id,
        Prediction.simulation_generated_at.is_not(None), Prediction.window_start >= since,
    ).order_by(Prediction.window_start, Prediction.id)).all()
    evaluations = db.scalars(select(PredictionEvaluation).where(
        PredictionEvaluation.run_id == run_id, PredictionEvaluation.provider_id == provider_id,
        PredictionEvaluation.simulation_time >= since,
    ).order_by(PredictionEvaluation.simulation_time)).all()
    contracts = db.scalars(select(BarterContract).where(
        BarterContract.run_id == run_id,
        (BarterContract.provider_id == provider_id) | (BarterContract.consumer_id == provider_id),
    ).order_by(BarterContract.id.desc())).all()
    transactions = db.scalars(select(CreditTransaction).where(
        CreditTransaction.run_id == run_id, CreditTransaction.provider_id == provider_id,
    ).order_by(CreditTransaction.id)).all()
    reputation = db.scalars(select(ReputationHistory).where(
        ReputationHistory.run_id == run_id, ReputationHistory.provider_id == provider_id,
    ).order_by(ReputationHistory.id)).all()
    reservations = [item for item in contracts if item.provider_id == provider_id and item.status in {
        ContractStatus.PROPOSED, ContractStatus.SCHEDULED, ContractStatus.AT_RISK, ContractStatus.ACTIVE,
    }]
    stochastic_events = db.scalars(select(StochasticEvent).where(
        StochasticEvent.run_id == run_id, StochasticEvent.provider_id == provider_id,
    ).order_by(StochasticEvent.start_time.desc())).all()
    active_events = [item for item in stochastic_events if item.start_time <= state.current_time < item.end_time]
    return {
        "provider": provider,
        "resource_history": resource_history,
        "predictions": predictions,
        "evaluations": evaluations,
        "contracts": contracts,
        "transactions": transactions,
        "reputation_history": reputation,
        "future_reservations": reservations,
        "forecast_metrics": next(item for item in provider_forecast_metrics(db, run_id) if item["provider_id"] == provider_id),
        "current_volatility": resource_history[-1].volatility if resource_history else 0,
        "active_stochastic_events": active_events,
        "stochastic_events": stochastic_events,
        "historical_failures": [item for item in stochastic_events if item.event_type == "capacity_failure"],
        "emergency_contracts": sum(item.barter_type == "Emergency" for item in contracts),
        "predictive_contracts": sum(item.barter_type == "Predictive" for item in contracts),
    }


def credit_timelines(db: Session) -> list[dict]:
    run_id = get_or_create_state(db).current_run_id
    result = []
    for provider in db.scalars(select(Provider).order_by(Provider.id)).all():
        items = db.scalars(select(CreditTransaction).where(
            CreditTransaction.run_id == run_id,
            CreditTransaction.provider_id == provider.id,
            CreditTransaction.simulation_time.is_not(None),
        ).order_by(CreditTransaction.simulation_time, CreditTransaction.id)).all()
        result.append({
            "provider_id": provider.id, "provider_name": provider.name,
            "points": [{"time": item.simulation_time, "balance": item.balance_after, "type": item.transaction_type.value} for item in items],
        })
    return result
