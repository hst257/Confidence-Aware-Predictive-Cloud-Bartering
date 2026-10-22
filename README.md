# Confidence-Aware Predictive Cloud Bartering

Stable Phase 3 prototype of a real-time, seeded stochastic cloud federation. Ten providers generate noisy workloads and capacity events while a transparent simulated predictor estimates future demand. The marketplace uses prediction confidence, provider reputation, reservations, contracts, collateral, renegotiation, and emergency barter to move idle resources where they are needed.

## What is included

- FastAPI + SQLAlchemy REST backend with PostgreSQL and SQLite support
- React + Vite dashboard for providers, predictions, marketplace, contracts, reputation, analytics, and events
- Automatically seeded Cloud A–J demo data and provider-specific workload personalities
- Compact live service rows with click-through to detailed resource cards, telemetry, and provider audits
- Reproducible runs plus a fresh-random-seed mode
- Start, pause, resume, reset, step, and 1×–100× simulation clock controls
- Stable, Normal, Volatile, Failure Test, and Stress Test scenarios
- Seeded workload noise, spikes, drops, partial or full capacity failures, and automatic recovery
- Prediction cycles at +30m, +1h, +2h, and +4h horizons
- Five-minute forecast refreshes using the declared daily baseline, observed residual trends, and matured forecast errors
- Estimated target-time demand ranges and conservative delivery-window capacity bounds
- Confidence-aware safe commitments and a fixed 16% collateral rate
- Automatic multi-provider matching, future-capacity reservations, contract lifecycle, risk monitoring, and renegotiation
- Emergency reactive barter when a shortage reaches the current simulation state
- Forecast-error, confidence-calibration, shortage, resilience, credit, and predictive-versus-reactive analytics
- Manual spike, drop, and failure injection
- Persistent contract, credit, collateral, reputation, renegotiation, shortage, run, and system-event histories

## Run locally

Prerequisites: Python 3.11+, Node 20+, and Docker, or an existing PostgreSQL 14+ server.

1. Start PostgreSQL:

   ```powershell
   docker compose up -d postgres
   ```

2. Start the API:

   ```powershell
   cd backend
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   Copy-Item ..\.env.example .env
   uvicorn app.main:app --reload
   ```

3. In a second terminal, start the UI:

   ```powershell
   cd frontend
   npm install
   npm run dev
   ```

Open <http://localhost:5173>. API documentation is at <http://localhost:8000/docs>.

The tables and ten demo providers are created automatically on API startup. Existing four-provider databases gain the six new providers without resetting their run, balances, or contracts. The included container publishes PostgreSQL on host port `55432`. For a quick backend-only run without Docker, set `DATABASE_URL=sqlite:///./cloud_barter.db` in `backend/.env`.

## Simulation walkthrough

1. Choose a scenario and reproducible seed, then press **Apply & restart**.
2. Select a speed and press **Start**, or use **Step +5m** for exact paused progression.
3. Watch workload observations, prediction cycles, deficits, safe surplus capacity, reservations, and contracts update together.
   **Live overview** lists all ten services in compact rows. Click a row to open **Service details**, immediately below it in the sidebar, with that service selected. This page retains all ten detailed resource cards and the selected service's telemetry; **View details** opens its full audit.
4. Open **Predictions** to inspect the four future horizons and confidence-aware safe commitments.
5. Inject a spike, drop, or capacity failure for a selected provider and observe risk, renegotiation, or emergency recovery events.
6. Use **Same seed** to return to Day 1 at 08:00 and reproduce the same stochastic workload and event schedule.

At 100×, one simulated hour takes about 36 real seconds. Wall-clock speed does not change the deterministic outcome of a seeded run.

The **Phase 1 manual lab** remains available for the original fixed teaching sequence: generate predictions, run matching, create a contract, revise the prediction, activate and complete contracts, or simulate a provider failure.

## Proactive allocation

Automatic allocation considers all four horizons, earliest window first. It subtracts incoming coverage separately for each overlapping time segment and combines suppliers, including CPU-only and RAM-only offers. The former three-hour cooldown no longer blocks other uncovered windows. Supplier reservations use peak concurrent commitments, not the sum of unrelated future reservations.

The predictor fits a damped residual level/trend around each declared workload profile. It no longer adds artificial forecast noise. Target-time error ranges use matured errors for the same horizon, with an observed-spread/cold-start fallback. Safe supply and anticipated demand use the upper estimate across the full delivery window. The baseline is still a simulator prior, not a model trained on external cloud telemetry; future stochastic events and future resource observations remain hidden. Confidence blends a bounded prior score with observed interval coverage and is not a probability guarantee.

Prediction responses add nullable `cpu_lower_bound`, `cpu_upper_bound`, `ram_lower_bound`, `ram_upper_bound`, `planning_cpu_upper`, and `planning_ram_upper`, plus observation/calibration sample counts. Hover over predicted usage, direction, or confidence in the existing table for their explanations. Older/manual predictions have no ranges. Startup adds compatible columns without deleting history or resetting the run. Existing emergency contracts remain emergency contracts; the new policy takes effect on subsequent forecast cycles.

Short rolling reservations are priced proportionally to their delivery duration at the configured hourly CPU/RAM rates. The original fixed-price manual lab is unchanged. Pooled allocations and automatic replacements are atomic: failed funding leaves no partial contracts or collateral. Emergency fallback checks growing shortages even after an earlier prevention, and counts deliverable supplier capacity rather than face-value promises.

### Seeded policy comparison

`backend/scripts/evaluate_proactive.py` uses fresh in-memory databases; it never resets the live application. It measures physically deliverable advance coverage per provider-minute, unresolved provider-minutes, point forecast MAE, lead time, and unused reserved CPU/RAM time. Contract counts alone are not a quality measure.

```powershell
cd backend
.venv\Scripts\python.exe scripts/evaluate_proactive.py --cases Normal:4281 Volatile:9017 --output benchmarks/proactive_after.json
```

For a previous-policy replay, pass `--backend-root` pointing to an archived backend from commit `eb8384e5da3cb1c69fbb0119b1cf822a750cb5c9`; the same evaluator supports both versions. Compare workload hashes before interpreting results. Results cover a small seeded experiment, not a general accuracy guarantee. Reports are in `backend/benchmarks/`.

## Architecture

```text
backend/app/
  models/             SQLAlchemy entities and lifecycle enums
  routers/            REST endpoints
  services/           matching, contracts, credits, reputation, and renegotiation
  simulation/         clock, predictor, seeded RNG, workloads, events, failures, and runs
frontend/src/
  components/         reusable controls, charts, logs, and contract details
  pages/              Phase 3 workflow and analytics views
```

The prediction engine is deliberately small and explainable. It blends the provider's deterministic workload profile with the latest observed state, adds seeded forecast error, and lowers confidence for longer horizons, volatile recent history, and lower provider reliability. It never reads future resource states or future stochastic events.

Core economic and matching formulas are centralized in `backend/app/config.py`; scenario probabilities live in `backend/app/simulation/scenario_presets.py`; provider workload behavior lives in `backend/app/simulation/workload_profiles.py`.

## Tests

```powershell
cd backend
.venv\Scripts\python.exe -m pytest -q

cd ..\frontend
npm run build
```

The integration suite covers the original Phase 1 contract workflow, deterministic and random Phase 3 simulation controls, prediction horizons and confidence safety, automatic predictive contracts and fixed collateral, future reservations, failure recovery, API validation, and same-seed reproducibility.

Focused tests in `backend/tests/test_proactive_planning.py` cover multi-supplier allocation, all horizons, partial-window top-ups, idempotence, reservation concurrency, duration pricing, atomic budget rollback, impaired delivery, emergency retries, and future-observation leakage. Set `TEST_DATABASE_URL` to a temporary SQLite database for a fresh full-suite run; this is separate from the live `DATABASE_URL`.

Existing databases upgraded during Phase 4 may retain unused compatibility columns. Phase 3 does not expose or depend on them; they remain mapped only so rollback can operate safely against those databases without destructive schema changes.
