import os
import time
from concurrent.futures import ThreadPoolExecutor

os.environ["DATABASE_URL"] = "sqlite:///./test_cloud_barter.db"

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.database import SessionLocal
from app.main import app
from app.models import (
    Collateral,
    CollateralStatus,
    CreditTransaction,
    EventLog,
    PredictionEvaluation,
    ReputationHistory,
    SimulationState,
    StochasticEvent,
    ResourceState,
)


def post_ok(client: TestClient, path: str, **kwargs):
    response = client.post(path, **kwargs)
    assert response.status_code < 300, response.text
    return response.json()


def put_ok(client: TestClient, path: str, **kwargs):
    response = client.put(path, **kwargs)
    assert response.status_code < 300, response.text
    return response.json()


def current_run_id() -> int:
    with SessionLocal() as db:
        return db.get(SimulationState, 1).current_run_id


def run_signature(client: TestClient) -> tuple:
    providers = client.get("/api/providers").json()
    resources = []
    for provider in providers:
        detail = client.get(f"/api/providers/{provider['id']}/analytics?range_minutes=240").json()
        resources.append((
            provider["name"],
            tuple((point["simulation_time"], point["cpu_usage"], point["ram_usage"], point["volatility"])
                  for point in detail["resource_history"]),
        ))
    snapshot = client.get("/api/simulation/snapshot?range_minutes=240").json()
    events = tuple((
        item["provider_name"], item["event_type"], item["name"], item["start_time"], item["end_time"],
        item["magnitude_percent"], item["capacity_loss_percent"], item["affected_resource"], item["severity"],
    ) for item in reversed(snapshot["stochastic_events"]))
    return tuple(resources), events


def test_complete_predictive_barter_workflow():
    with TestClient(app) as client:
        post_ok(client, "/api/simulation/reset")

        providers = client.get("/api/providers").json()
        assert [item["name"] for item in providers] == ["Cloud A", "Cloud B", "Cloud C", "Cloud D"]

        post_ok(client, "/api/simulation/generate-predictions")
        predictions = client.get("/api/predictions").json()
        cloud_a = next(item for item in predictions if item["provider_name"] == "Cloud A")
        assert (cloud_a["cpu_deficit"], cloud_a["ram_deficit"], cloud_a["confidence"]) == (30, 25, 91)

        matches = post_ok(client, "/api/matching/run")
        best = matches[0]
        assert (best["provider_name"], best["consumer_name"]) == ("Cloud B", "Cloud A")
        assert (best["cpu_amount"], best["ram_amount"], best["barter_cost"], best["collateral"]) == (30, 25, 60, 9.6)

        original = post_ok(
            client,
            "/api/contracts",
            json={
                "provider_id": best["provider_id"],
                "consumer_id": best["consumer_id"],
                "prediction_id": best["prediction_id"],
                "cpu_amount": best["cpu_amount"],
                "ram_amount": best["ram_amount"],
                "start_time": best["window_start"],
                "end_time": best["window_end"],
                "match_score": best["match_score"],
                "selection_reason": best["selection_reason"],
            },
        )
        assert original["status"] == "Scheduled"
        assert original["collateral"]["status"] == "Locked"

        renegotiated = post_ok(client, "/api/simulation/re-evaluate")
        assert len(renegotiated["affected_contract_ids"]) == 2

        contracts = client.get("/api/contracts").json()
        original_after = next(item for item in contracts if item["id"] == original["id"])
        assert original_after["status"] == "Renegotiated"
        replacements = sorted(
            [item for item in contracts if item["parent_contract_id"] == original["id"]],
            key=lambda item: item["provider_name"],
        )
        assert [(item["provider_name"], item["cpu_amount"], item["ram_amount"]) for item in replacements] == [
            ("Cloud B", 20, 15),
            ("Cloud C", 10, 10),
        ]

        started = post_ok(client, "/api/simulation/start-contracts")
        assert len(started["affected_contract_ids"]) == 2
        completed = post_ok(client, "/api/simulation/complete-contracts")
        assert len(completed["affected_contract_ids"]) == 2

        final_contracts = client.get("/api/contracts").json()
        assert all(item["status"] == "Completed" for item in final_contracts if item["parent_contract_id"] == original["id"])
        final_providers = {item["name"]: item for item in client.get("/api/providers").json()}
        assert final_providers["Cloud A"]["credit_balance"] == 120
        assert final_providers["Cloud B"]["credit_balance"] == 259
        assert final_providers["Cloud C"]["credit_balance"] == 226
        assert final_providers["Cloud B"]["successful_contracts"] == 1
        assert final_providers["Cloud C"]["successful_contracts"] == 1

        events = client.get("/api/events").json()
        event_types = {event["event_type"] for event in events}
        assert {
            "prediction.deficit",
            "match.selected",
            "collateral.locked",
            "contract.renegotiated",
            "contract.activated",
            "credits.settled",
            "reputation.updated",
            "contract.completed",
        }.issubset(event_types)

        with SessionLocal() as db:
            run_id = db.get(SimulationState, 1).current_run_id
            assert not db.scalars(select(Collateral).where(
                Collateral.run_id == run_id, Collateral.status == CollateralStatus.LOCKED,
            )).all()
            assert len(db.scalars(select(CreditTransaction).where(CreditTransaction.run_id == run_id)).all()) >= 10
            assert len(db.scalars(select(ReputationHistory).where(ReputationHistory.run_id == run_id)).all()) == 4
            assert len(db.scalars(select(EventLog).where(EventLog.run_id == run_id)).all()) >= 20


def test_failure_forfeits_collateral_and_penalizes_scores():
    with TestClient(app) as client:
        post_ok(client, "/api/simulation/reset")
        post_ok(client, "/api/simulation/generate-predictions")
        best = post_ok(client, "/api/matching/run")[0]
        contract = post_ok(
            client,
            "/api/contracts",
            json={
                "provider_id": best["provider_id"],
                "consumer_id": best["consumer_id"],
                "prediction_id": best["prediction_id"],
                "cpu_amount": best["cpu_amount"],
                "ram_amount": best["ram_amount"],
                "start_time": best["window_start"],
                "end_time": best["window_end"],
                "match_score": best["match_score"],
                "selection_reason": best["selection_reason"],
            },
        )
        post_ok(client, f"/api/contracts/{contract['id']}/fail")
        failed = client.get(f"/api/contracts/{contract['id']}").json()["contract"]
        assert failed["status"] == "Failed"
        assert failed["collateral"]["status"] == "Forfeited"
        providers = {item["name"]: item for item in client.get("/api/providers").json()}
        assert providers["Cloud A"]["credit_balance"] == 189.6
        assert providers["Cloud B"]["forecast_reliability"] == 81
        assert providers["Cloud B"]["sla_reputation"] == 90
        assert providers["Cloud B"]["failed_predictions"] == 1


def test_phase3_clock_drives_stochastic_forecasts_and_preserves_lifecycle():
    with TestClient(app) as client:
        post_ok(client, "/api/simulation/reset")
        initial = client.get("/api/simulation/state").json()
        assert (initial["day"], initial["clock"], initial["running"], initial["speed"]) == (1, "08:00:00", False, 25)

        speed = client.patch("/api/simulation/speed", json={"speed": 100})
        assert speed.status_code == 200
        assert speed.json()["speed"] == 100
        post_ok(client, "/api/simulation/start")
        time.sleep(0.6)
        moving = client.get("/api/simulation/state").json()
        assert moving["running"] is True
        assert moving["current_time"] > initial["current_time"]
        paused = post_ok(client, "/api/simulation/pause")
        assert paused["running"] is False

        # The live clock produces observations and reforecasts without manual data entry.
        stepped = post_ok(client, "/api/simulation/step", json={"minutes": 125})
        assert stepped["clock"] >= "10:05:00"
        snapshot = client.get("/api/simulation/snapshot").json()
        assert len(snapshot["selected_provider"]["resource_history"]) >= 120
        assert len(snapshot["predictions"]) >= 4
        assert all(item["recent_volatility"] >= 0 for item in snapshot["predictions"])
        assert all(item["run_id"] == snapshot["simulation"]["run_id"] for item in snapshot["predictions"])

        # Cross several forecast horizons; Phase 1 lifecycle contracts remain valid
        # while observation-only forecasts are evaluated against stochastic truth.
        post_ok(client, "/api/simulation/step", json={"minutes": 180})
        finished = client.get("/api/simulation/snapshot").json()
        assert sum(item["predictions_evaluated"] for item in finished["analytics"]["forecast_metrics"]) > 0
        assert sum(item["prediction_count"] for item in finished["analytics"]["confidence_calibration"]) > 0
        assert 0 <= finished["analytics"]["system_resilience_score"] <= 100
        event_types = {item["event_type"] for item in finished["events"]}
        assert {"prediction.cycle_started", "prediction.evaluated"}.issubset(event_types)

        resumed = post_ok(client, "/api/simulation/resume")
        assert resumed["running"] is True
        post_ok(client, "/api/simulation/pause")


def test_same_seed_reproduces_full_stochastic_run_and_different_seed_diverges():
    with TestClient(app) as client:
        configured = put_ok(client, "/api/simulation/configure", json={
            "scenario": "Stress Test", "seed": 240319, "random_mode": False,
        })
        assert (configured["scenario"], configured["seed"]) == ("Stress Test", 240319)
        post_ok(client, "/api/simulation/step", json={"minutes": 180})
        first_run = current_run_id()
        first_signature = run_signature(client)
        assert first_signature[1], "Stress Test should produce seeded stochastic events"

        restarted = post_ok(client, "/api/simulation/restart-same-seed")
        assert restarted["run_id"] != first_run
        assert restarted["seed"] == 240319
        post_ok(client, "/api/simulation/step", json={"minutes": 180})
        assert run_signature(client) == first_signature

        put_ok(client, "/api/simulation/configure", json={
            "scenario": "Stress Test", "seed": 240320, "random_mode": False,
        })
        post_ok(client, "/api/simulation/step", json={"minutes": 180})
        assert run_signature(client) != first_signature
        runs = client.get("/api/simulation/runs").json()
        assert len(runs) >= 3
        assert any(item["id"] == first_run and item["final_statistics"] for item in runs)


def test_manual_failure_is_visible_and_triggers_reactive_recovery_path():
    with TestClient(app) as client:
        put_ok(client, "/api/simulation/configure", json={
            # Seed 4 deterministically yields a 100% manual failure, guaranteeing
            # that the reactive path is exercised regardless of baseline load.
            "scenario": "Failure Test", "seed": 4, "random_mode": False,
        })
        cloud_d = next(item for item in client.get("/api/providers").json() if item["name"] == "Cloud D")
        injected = post_ok(client, "/api/simulation/events/inject", json={
            "provider_id": cloud_d["id"], "kind": "failure", "severity": "critical",
        })
        assert injected["event_id"] > 0
        post_ok(client, "/api/simulation/step", json={"minutes": 1})
        snapshot = client.get("/api/simulation/snapshot").json()
        failure = next(item for item in snapshot["stochastic_events"] if item["id"] == injected["event_id"])
        assert failure["source"] == "manual"
        assert failure["event_type"] == "capacity_failure"
        assert failure["active"] is True
        provider = next(item for item in snapshot["providers"] if item["id"] == cloud_d["id"])
        assert provider["active_event"] == failure["name"]
        assert max(provider["capacity_lost_cpu"], provider["capacity_lost_ram"]) > 0
        assert snapshot["shortages"]
        assert snapshot["shortages"][0]["outcome"] in {"Recovered", "Unresolved"}
        assert "emergency.initiated" in {item["event_type"] for item in snapshot["events"]}

        with SessionLocal() as db:
            run_id = db.get(SimulationState, 1).current_run_id
            assert db.scalars(select(StochasticEvent).where(StochasticEvent.run_id == run_id)).all()
            assert db.scalars(select(PredictionEvaluation).where(PredictionEvaluation.run_id == run_id)).all() == []


def test_phase3_simulated_predictions_are_deterministic_and_confidence_aware():
    with TestClient(app) as client:
        put_ok(client, "/api/simulation/configure", json={
            "scenario": "Normal", "seed": 4281, "random_mode": False,
        })
        post_ok(client, "/api/simulation/step", json={"minutes": 130})
        active = client.get("/api/predictions").json()
        assert len(active) == 4 * 4
        assert {item["horizon_minutes"] for item in active} == {30, 60, 120, 240}
        assert all(item["safe_cpu_commitment"] <= item["predicted_cpu_spare"] for item in active)
        assert all(item["safe_ram_commitment"] <= item["predicted_ram_spare"] for item in active)
        long_range = {item["provider_name"]: item for item in active if item["horizon_minutes"] == 240}
        assert long_range["Cloud A"]["confidence"] > long_range["Cloud D"]["confidence"]
        assert "model_name" not in active[0]
        assert client.get("/api/forecasting/models").status_code == 404
        assert client.get("/api/experiments/comparison").status_code == 404
        snapshot = client.get("/api/simulation/snapshot").json()
        assert sum(item["predictions_evaluated"] for item in snapshot["analytics"]["forecast_metrics"]) > 0


def test_phase3_automatic_barter_reserves_capacity_with_fixed_collateral():
    with TestClient(app) as client:
        put_ok(client, "/api/simulation/configure", json={
            "scenario": "Normal", "seed": 4281, "random_mode": False,
        })
        post_ok(client, "/api/simulation/step", json={"minutes": 1})
        contracts = client.get("/api/contracts").json()
        assert contracts and all(item["barter_type"] == "Predictive" for item in contracts)
        for contract in contracts:
            assert contract["collateral"]["amount"] == round(contract["barter_cost"] * 0.16, 2)
        providers = {item["id"]: item for item in client.get("/api/providers").json()}
        assert any(providers[item["provider_id"]]["future_commitment_cpu"] > 0 for item in contracts)


def test_phase3_failure_triggers_automatic_pre_start_renegotiation():
    with TestClient(app) as client:
        put_ok(client, "/api/simulation/configure", json={
            "scenario": "Normal", "seed": 4281, "random_mode": False,
        })
        post_ok(client, "/api/simulation/step", json={"minutes": 1})
        scheduled = next(
            item for item in client.get("/api/contracts").json()
            if item["status"] == "Scheduled" and item["barter_type"] == "Predictive"
        )

        # At 10:00 the +2h prediction revisits this contract's 12:00 start.
        # A just-injected capacity failure must make it unsafe before activation.
        post_ok(client, "/api/simulation/step", json={"minutes": 114})
        post_ok(client, "/api/simulation/events/inject", json={
            "provider_id": scheduled["provider_id"], "kind": "failure", "severity": "critical",
        })
        post_ok(client, "/api/simulation/step", json={"minutes": 5})

        snapshot = client.get("/api/simulation/snapshot").json()
        original = next(item for item in snapshot["contracts"] if item["id"] == scheduled["id"])
        replacements = [item for item in snapshot["contracts"] if item["parent_contract_id"] == scheduled["id"]]
        event_types = {item["event_type"] for item in snapshot["events"]}
        assert original["status"] == "Renegotiated"
        assert replacements
        assert snapshot["renegotiations"]
        assert {"contract.at_risk", "renegotiation.started", "contract.renegotiated"}.issubset(event_types)


def test_phase3_accepts_every_speed_and_all_manual_event_types():
    with TestClient(app) as client:
        put_ok(client, "/api/simulation/configure", json={
            "scenario": "Stable", "seed": 9017, "random_mode": False,
        })
        for speed in (1, 2, 5, 10, 25, 50, 100):
            response = client.patch("/api/simulation/speed", json={"speed": speed})
            assert response.status_code == 200
            assert response.json()["speed"] == speed

        providers = client.get("/api/providers").json()
        for provider, kind in zip(providers[:3], ("spike", "drop", "failure")):
            post_ok(client, "/api/simulation/events/inject", json={
                "provider_id": provider["id"], "kind": kind, "severity": "warning",
            })
        event_types = {item["event_type"] for item in client.get("/api/simulation/snapshot").json()["stochastic_events"]}
        assert {"workload_spike", "workload_drop", "capacity_failure"}.issubset(event_types)


def test_prediction_cycle_recovers_when_a_run_temporarily_has_no_history():
    with TestClient(app) as client:
        post_ok(client, "/api/simulation/reset")
        with SessionLocal() as db:
            run_id = db.get(SimulationState, 1).current_run_id
            db.execute(delete(ResourceState).where(ResourceState.run_id == run_id))
            db.commit()

        stepped = post_ok(client, "/api/simulation/step", json={"minutes": 1})
        assert stepped["clock"] == "08:01:00"
        events = client.get("/api/events?event_type=prediction.cycle_skipped").json()
        assert events and "no observations" in events[0]["message"]
        snapshot = client.get("/api/simulation/snapshot").json()
        assert len(snapshot["selected_provider"]["resource_history"]) == 1


def test_overlapping_simulation_controls_do_not_corrupt_the_shared_clock():
    with TestClient(app) as client:
        post_ok(client, "/api/simulation/reset")

        def perform(index: int):
            if index % 3 == 0:
                return client.post("/api/simulation/reset")
            if index % 3 == 1:
                return client.post("/api/simulation/step", json={"minutes": 2})
            return client.post("/api/simulation/start")

        with ThreadPoolExecutor(max_workers=6) as pool:
            responses = list(pool.map(perform, range(18)))
        assert all(response.status_code < 500 for response in responses)

        paused = post_ok(client, "/api/simulation/pause")
        assert paused["running"] is False
        assert client.get("/api/simulation/snapshot").status_code == 200
