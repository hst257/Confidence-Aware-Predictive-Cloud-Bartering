from datetime import timedelta
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database import Base
from app.models import BarterContract, Collateral, CreditTransaction, Prediction, Provider, ResourceState, ShortageEvent, SimulationState
from app.services.automatic_marketplace_service import auto_match_and_create
from app.services.contract_service import create_contract
from app.services.demo_service import reset_demo
from app.services.emergency_matching_service import _incoming, process_current_shortages
from app.services.reservation_service import overlaps, peak
from app.simulation.adaptive_forecast import estimate
from app.simulation.engine import _future_reservations, advance_to
from app.simulation.prediction_generator import generate_simulation_predictions


@pytest.fixture
def market():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine, autoflush=False, expire_on_commit=False) as db:
        reset_demo(db, seed=4281, scenario="Stable", random_mode=False)
        providers = db.scalars(select(Provider).order_by(Provider.id)).all()
        for provider in providers:
            provider.credit_balance = 1000
        db.flush()
        yield db, db.get(SimulationState, 1), providers
    engine.dispose()


def prediction(db, state, provider, *, ahead=30, cpu=0, ram=0, demand=False):
    start = state.current_time + timedelta(minutes=ahead)
    item = Prediction(
        run_id=state.current_run_id, provider_id=provider.id,
        predicted_cpu_usage=provider.total_cpu + cpu if demand else max(0, provider.total_cpu - cpu),
        predicted_ram_usage=provider.total_ram + ram if demand else max(0, provider.total_ram - ram),
        predicted_cpu_spare=0 if demand else cpu, predicted_ram_spare=0 if demand else ram,
        cpu_deficit=cpu if demand else 0, ram_deficit=ram if demand else 0,
        safe_cpu_commitment=0 if demand else cpu, safe_ram_commitment=0 if demand else ram,
        confidence=90, horizon_minutes=ahead, window_start=start,
        window_end=start + timedelta(hours=1), simulation_generated_at=state.current_time,
        cycle_id="fixture", kind="Initial",
    )
    db.add(item)
    db.flush()
    return item


def contract(db, state, supplier, consumer, *, start=30, end=90, cpu=0, ram=0, kind="Predictive"):
    return create_contract(db, provider_id=supplier.id, consumer_id=consumer.id,
        prediction_id=None, cpu_amount=cpu, ram_amount=ram,
        start_time=state.current_time + timedelta(minutes=start),
        end_time=state.current_time + timedelta(minutes=end), match_score=90,
        selection_reason="Reservation fixture", simulation_time=state.current_time,
        barter_type=kind, commit=False)


def test_pools_cpu_only_and_ram_only_suppliers_and_is_idempotent(market):
    db, state, providers = market
    consumer, cpu_supplier, ram_supplier = providers[:3]
    prediction(db, state, consumer, cpu=20, ram=20, demand=True)
    prediction(db, state, cpu_supplier, cpu=20)
    prediction(db, state, ram_supplier, ram=20)
    created = auto_match_and_create(db, "fixture", state.current_time)
    assert len(created) == 2
    contracts = db.scalars(select(BarterContract)).all()
    assert sum(item.cpu_amount for item in contracts) == 20
    assert sum(item.ram_amount for item in contracts) == 20
    assert all(item.start_time > item.created_simulation_time and item.barter_type == "Predictive" for item in contracts)
    assert auto_match_and_create(db, "fixture", state.current_time) == []


def test_all_horizons_allocate_only_uncovered_time_windows(market):
    db, state, providers = market
    for ahead in (30, 60, 120, 240):
        prediction(db, state, providers[0], ahead=ahead, cpu=10, demand=True)
        prediction(db, state, providers[1], ahead=ahead, cpu=40)
    created = auto_match_and_create(db, "fixture", state.current_time)
    assert len(created) == 4
    for minute in (30, 75, 110, 150, 270):
        start = state.current_time + timedelta(minutes=minute)
        end = start + timedelta(minutes=1)
        covered = peak(overlaps(db, state.current_run_id, providers[0].id, start, end, incoming=True), start, end)
        assert covered == (10, 0)
    assert auto_match_and_create(db, "fixture", state.current_time) == []


def test_partial_coverage_is_topped_up_and_emergency_does_not_block_later_windows(market):
    db, state, providers = market
    consumer, supplier, backup = providers[:3]
    contract(db, state, backup, consumer, start=0, end=10, cpu=10, kind="Emergency")
    contract(db, state, backup, consumer, start=30, end=60, cpu=4)
    db.flush()
    prediction(db, state, consumer, cpu=10, demand=True)
    prediction(db, state, supplier, cpu=30)
    ids = auto_match_and_create(db, "fixture", state.current_time)
    assert len(ids) == 2
    additions = [db.get(BarterContract, item) for item in ids]
    assert [(item.cpu_amount, (item.end_time - item.start_time).total_seconds() / 60) for item in additions] == [(6, 30), (10, 30)]
    assert [item.barter_cost for item in additions] == [4.5, 7.5]


def test_supplier_reservations_use_peak_concurrency_not_sum_of_disjoint_windows(market):
    db, state, providers = market
    consumer, supplier, other = providers[:3]
    contract(db, state, supplier, other, start=30, end=60, cpu=20)
    contract(db, state, supplier, other, start=60, end=90, cpu=20)
    db.flush()
    prediction(db, state, consumer, cpu=10, demand=True)
    prediction(db, state, supplier, cpu=30)
    assert len(auto_match_and_create(db, "fixture", state.current_time)) == 1
    start, end = state.current_time + timedelta(minutes=30), state.current_time + timedelta(minutes=90)
    assert peak(overlaps(db, state.current_run_id, supplier.id, start, end), start, end) == (30, 0)
    assert _future_reservations(db, state.current_run_id, supplier.id, state.current_time) == (0, 0)


def test_insufficient_budget_and_failed_pooled_commit_leave_no_partial_economics(market):
    db, state, providers = market
    prediction(db, state, providers[0], cpu=20, ram=20, demand=True)
    prediction(db, state, providers[1], cpu=20)
    prediction(db, state, providers[2], ram=20)
    providers[0].credit_balance = 0
    db.flush()
    assert auto_match_and_create(db, "fixture", state.current_time) == []
    providers[0].credit_balance = 1000
    db.flush()
    balances = {provider.id: provider.credit_balance for provider in providers}
    calls = 0

    def fail_second(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise HTTPException(409, "Collateral no longer available")
        return create_contract(*args, **kwargs)

    with patch("app.services.automatic_marketplace_service.create_contract", side_effect=fail_second):
        assert auto_match_and_create(db, "fixture", state.current_time) == []
    assert not db.scalars(select(BarterContract)).all()
    assert not db.scalars(select(Collateral)).all()
    assert not db.scalars(select(CreditTransaction)).all()
    assert {provider.id: provider.credit_balance for provider in providers} == balances


def test_persistent_outage_cannot_supply_a_stale_optimistic_forecast(market):
    db, state, providers = market
    prediction(db, state, providers[0], cpu=10, demand=True)
    prediction(db, state, providers[1], cpu=30)
    observed = db.scalar(select(ResourceState).where(ResourceState.provider_id == providers[1].id))
    observed.cpu_capacity_lost = providers[1].total_cpu
    observed.usable_cpu = observed.cpu_available = 0
    db.flush()
    assert auto_match_and_create(db, "fixture", state.current_time) == []


def test_forecast_uses_recent_trend_and_matured_error_not_random_noise():
    history = [(minute, 50 + minute * .4, 50) for minute in range(15)]
    near = estimate(history, [(0, 50), (30, 55)], [], 100, 30, 1)
    far = estimate(history, [(0, 50), (30, 55)], [], 100, 240, 1)
    assert near.mean > far.mean >= 50
    assert near.lower <= near.mean <= near.upper <= near.window_upper
    wide = estimate(history, [(0, 50), (30, 55)], [-15, 15] * 8, 100, 30, 1)
    assert wide.upper - wide.lower > near.upper - near.lower
    assert near == estimate(history, [(0, 50), (30, 55)], [], 100, 30, 1)


def test_future_observations_cannot_change_current_forecasts(market):
    db, state, providers = market
    first = generate_simulation_predictions(db, state.current_time)
    db.flush()
    signature = lambda rows: [(item.provider_id, item.horizon_minutes, item.predicted_cpu_usage,
        item.predicted_ram_usage, item.cpu_lower_bound, item.cpu_upper_bound, item.planning_cpu_upper) for item in rows]
    before = signature(first)
    for provider in providers:
        db.add(ResourceState(run_id=state.current_run_id, provider_id=provider.id,
            simulation_time=state.current_time + timedelta(minutes=30), cpu_usage=9999, ram_usage=9999,
            usable_cpu=0, usable_ram=0))
    db.flush()
    assert signature(generate_simulation_predictions(db, state.current_time)) == before


def test_shortage_growth_after_prevention_still_gets_emergency_backup(market):
    db, state, providers = market
    consumer, supplier = providers[:2]
    observed = db.scalar(select(ResourceState).where(ResourceState.provider_id == consumer.id))
    observed.cpu_usage = observed.usable_cpu + 5
    original = contract(db, state, supplier, consumer, start=0, end=60, cpu=5)
    original.status = "Active"
    db.flush()
    process_current_shortages(db, state.current_time)
    db.flush()
    assert db.scalar(select(ShortageEvent)).resolution_type == "Predictive"
    observed.cpu_usage = observed.usable_cpu + 12
    db.flush()
    process_current_shortages(db, state.current_time)
    db.flush()
    emergencies = db.scalars(select(BarterContract).where(BarterContract.barter_type == "Emergency")).all()
    assert emergencies and sum(item.cpu_amount for item in emergencies) >= 7
    count = len(emergencies)
    process_current_shortages(db, state.current_time)
    db.flush()
    assert len(db.scalars(select(BarterContract).where(BarterContract.barter_type == "Emergency")).all()) == count


def test_incoming_coverage_does_not_count_undeliverable_promises(market):
    db, state, providers = market
    consumer, supplier, other = providers[:3]
    contract(db, state, supplier, consumer, start=0, end=60, cpu=20)
    contract(db, state, supplier, other, start=0, end=60, cpu=20)
    observed = db.scalar(select(ResourceState).where(ResourceState.provider_id == supplier.id))
    observed.cpu_available = 10
    db.flush()
    assert _incoming(db, state.current_run_id, consumer.id, state.current_time, "Predictive") == (5, 0)


def test_upgraded_cadence_does_not_backdate_forecasts_or_reservations(market):
    db, state, _ = market
    state.last_prediction_at = state.current_time
    state.current_time += timedelta(minutes=9, seconds=57)
    state.last_sample_at = state.current_time.replace(second=0)
    now = state.current_time
    advance_to(db, now + timedelta(minutes=5))
    db.flush()
    predictions = db.scalars(select(Prediction)).all()
    assert predictions and all(item.simulation_generated_at >= now for item in predictions)
    assert all(item.created_simulation_time >= now for item in db.scalars(select(BarterContract)).all())
