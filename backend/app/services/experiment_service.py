from __future__ import annotations

import csv
import io
import json
from statistics import mean, median, pstdev

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import SimulationRun
METRICS = [
    "shortages_prevented", "emergency_contracts", "unresolved_shortages",
    "total_cpu_utilization", "collateral_penalties", "contract_success_rate",
    "average_forecast_accuracy", "system_resilience_score", "average_reaction_time",
    "average_prediction_lead_time", "renegotiations", "failed_contracts",
]


def compare_runs(db: Session, run_ids: list[int] | None = None) -> dict:
    query = select(SimulationRun).order_by(SimulationRun.id.desc())
    if run_ids:
        query = query.where(SimulationRun.id.in_(run_ids))
    runs = db.scalars(query.limit(100)).all()
    rows = []
    for run in runs:
        stats = run.final_statistics or {}
        rows.append({
            "run_id": run.id, "seed": run.seed, "scenario": run.scenario,
            "forecast_model": run.forecast_model, "bartering_strategy": run.bartering_strategy,
            "training_window_minutes": run.training_window_minutes,
            "safety_margin_multiplier": run.safety_margin_multiplier,
            "duration_minutes": run.simulation_duration_minutes, "status": run.status,
            **{metric: float(stats.get(metric, 0) or 0) for metric in METRICS},
        })
    grouped = []
    for strategy in ["Reactive Only", "Predictive", "Confidence-Aware Predictive"]:
        items = [row for row in rows if row["bartering_strategy"] == strategy]
        if not items:
            continue
        summaries = {}
        for metric in METRICS:
            values = [item[metric] for item in items]
            summaries[metric] = {
                "mean": round(mean(values), 3), "median": round(median(values), 3),
                "min": round(min(values), 3), "max": round(max(values), 3),
                "stddev": round(pstdev(values), 3) if len(values) > 1 else 0,
            }
        grouped.append({"strategy": strategy, "run_count": len(items), "metrics": summaries})
    return {"metrics": METRICS, "runs": rows, "strategy_summary": grouped}


def export_runs(db: Session, run_ids: list[int] | None, export_format: str) -> tuple[str, str]:
    comparison = compare_runs(db, run_ids)
    if export_format == "json":
        return json.dumps(comparison, indent=2), "application/json"
    output = io.StringIO()
    fields = ["run_id", "seed", "scenario", "forecast_model", "bartering_strategy", "training_window_minutes", "safety_margin_multiplier", "duration_minutes", "status", *METRICS]
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    writer.writerows(comparison["runs"])
    return output.getvalue(), "text/csv"
