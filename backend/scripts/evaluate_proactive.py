"""Replay seeded workloads in fresh in-memory databases, never the live database.

Run from backend: python scripts/evaluate_proactive.py --output report.json
Metrics count provider-minutes, not potentially fragmented contract rows.
"""

import argparse
import hashlib
import json
from datetime import timedelta
from pathlib import Path
import sys

bootstrap = argparse.ArgumentParser(add_help=False)
bootstrap.add_argument("--backend-root", type=Path)
root_options, _ = bootstrap.parse_known_args()
sys.path.insert(0, str(root_options.backend_root or Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import Base
from app.models import BarterContract, ContractStatus, PredictionEvaluation, ResourceState, SimulationState
from app.services.demo_service import reset_demo
from app.simulation.engine import advance_to


def replay(seed: int, scenario: str, minutes: int) -> dict:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    digest = hashlib.sha256()
    shortage_minutes = prevented_minutes = unresolved_minutes = 0
    cpu_reserved = cpu_unused = ram_reserved = ram_unused = 0.0
    try:
        with Session(engine, autoflush=False, expire_on_commit=False) as db:
            reset_demo(db, seed=seed, scenario=scenario, random_mode=False)
            state = db.get(SimulationState, 1)
            for minute_index in range(minutes):
                now = state.current_time + timedelta(minutes=1)
                advance_to(db, now)
                db.commit()
                observations = db.scalars(select(ResourceState).where(ResourceState.simulation_time == now).order_by(ResourceState.provider_id)).all()
                contracts = db.scalars(select(BarterContract).where(
                    BarterContract.status == ContractStatus.ACTIVE,
                    BarterContract.start_time <= now, BarterContract.end_time > now,
                )).all()
                capacity = {point.provider_id: point for point in observations}
                outgoing = {}
                for item in contracts:
                    cpu, ram = outgoing.get(item.provider_id, (0, 0))
                    outgoing[item.provider_id] = cpu + item.cpu_amount, ram + item.ram_amount

                def delivered(item):
                    point = capacity[item.provider_id]
                    cpu, ram = outgoing[item.provider_id]
                    return (item.cpu_amount * min(1, point.cpu_available / cpu) if cpu else 0,
                        item.ram_amount * min(1, point.ram_available / ram) if ram else 0)

                for point in observations:
                    digest.update(json.dumps((point.provider_id, str(now), point.cpu_usage, point.ram_usage, point.usable_cpu, point.usable_ram)).encode())
                    cpu_need = max(0, point.cpu_usage - point.usable_cpu)
                    ram_need = max(0, point.ram_usage - point.usable_ram)
                    incoming = [item for item in contracts if item.consumer_id == point.provider_id]
                    predicted = [item for item in incoming if item.barter_type == "Predictive"]
                    cpu = sum(item.cpu_amount for item in predicted)
                    ram = sum(item.ram_amount for item in predicted)
                    cpu_reserved += cpu
                    ram_reserved += ram
                    cpu_unused += max(0, cpu - cpu_need)
                    ram_unused += max(0, ram - ram_need)
                    if cpu_need <= state.configuration["emergency_threshold"] and ram_need <= state.configuration["emergency_threshold"]:
                        continue
                    shortage_minutes += 1
                    if sum(delivered(item)[0] for item in predicted) + 0.01 >= cpu_need and sum(delivered(item)[1] for item in predicted) + 0.01 >= ram_need:
                        prevented_minutes += 1
                    if sum(delivered(item)[0] for item in incoming) + 0.01 < cpu_need or sum(delivered(item)[1] for item in incoming) + 0.01 < ram_need:
                        unresolved_minutes += 1
                if (minute_index + 1) % 60 == 0:
                    print(f"  {minute_index + 1}/{minutes} minutes; {prevented_minutes}/{shortage_minutes} shortage-minutes covered in advance", file=sys.stderr, flush=True)
            contracts = db.scalars(select(BarterContract)).all()
            predictive = [item for item in contracts if item.barter_type == "Predictive"]
            evaluations = db.scalars(select(PredictionEvaluation)).all()
            leads = [(item.start_time - item.created_simulation_time).total_seconds() / 60 for item in predictive if item.created_simulation_time]
            return {
                "scenario": scenario, "seed": seed, "minutes": minutes,
                "workload_sha256": digest.hexdigest(),
                "predictive_contracts": len(predictive),
                "emergency_contracts": len(contracts) - len(predictive),
                "shortage_provider_minutes": shortage_minutes,
                "prevented_provider_minutes": prevented_minutes,
                "prevention_percent": round(100 * prevented_minutes / max(shortage_minutes, 1), 2),
                "unresolved_provider_minutes": unresolved_minutes,
                "mean_advance_minutes": round(sum(leads) / max(len(leads), 1), 2),
                "unused_reserved_cpu_minutes": round(cpu_unused, 2),
                "reserved_cpu_minutes": round(cpu_reserved, 2),
                "unused_reserved_ram_gb_minutes": round(ram_unused, 2),
                "reserved_ram_gb_minutes": round(ram_reserved, 2),
                "cpu_mae": round(sum(item.cpu_absolute_error for item in evaluations) / max(len(evaluations), 1), 3),
                "ram_mae": round(sum(item.ram_absolute_error for item in evaluations) / max(len(evaluations), 1), 3),
            }
    finally:
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--minutes", type=int, default=360)
    parser.add_argument("--backend-root", type=Path, help="Optional archived backend for an identical replay of the previous policy")
    parser.add_argument("--cases", nargs="+", help="Explicit Scenario:seed pairs, e.g. Normal:4281 Volatile:9017")
    parser.add_argument("--seeds", type=int, nargs="+", default=[4281, 9017])
    parser.add_argument("--scenarios", nargs="+", default=["Normal", "Volatile"])
    parser.add_argument("--label", default="current")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    results = []
    cases = [(scenario, seed) for scenario in args.scenarios for seed in args.seeds]
    if args.cases:
        cases = [(item.rsplit(":", 1)[0], int(item.rsplit(":", 1)[1])) for item in args.cases]
    for scenario, seed in cases:
        print(f"Replaying {scenario}, seed {seed}, {args.minutes} minutes", file=sys.stderr, flush=True)
        result = replay(seed, scenario, args.minutes)
        results.append(result)
        print(json.dumps(result), file=sys.stderr, flush=True)
    report = {"label": args.label, "forecast_interval_minutes": get_settings().prediction_interval_minutes, "results": results}
    encoded = json.dumps(report, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
