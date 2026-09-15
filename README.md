# Confidence-Aware Predictive Cloud Bartering

Stable Phase 3 prototype of a real-time, seeded stochastic cloud federation. Four providers generate noisy workloads and capacity events while a transparent simulated predictor estimates future demand. The marketplace uses prediction confidence, provider reputation, reservations, contracts, collateral, renegotiation, and emergency barter to move idle resources where they are needed.

## What is included

- FastAPI + SQLAlchemy REST backend with PostgreSQL and SQLite support
- React + Vite dashboard for providers, predictions, marketplace, contracts, reputation, analytics, and events
- Automatically seeded Cloud A–D demo data and provider-specific workload personalities
- Reproducible runs plus a fresh-random-seed mode
- Start, pause, resume, reset, step, and 1×–100× simulation clock controls
- Stable, Normal, Volatile, Failure Test, and Stress Test scenarios
- Seeded workload noise, spikes, drops, partial or full capacity failures, and automatic recovery
- Prediction cycles at +30m, +1h, +2h, and +4h horizons
- Lightweight predictions based only on the current and historical simulated observations
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

The tables and four demo providers are created automatically on API startup. The included container publishes PostgreSQL on host port `55432`. For a quick backend-only run without Docker, set `DATABASE_URL=sqlite:///./cloud_barter.db` in `backend/.env`.

## Simulation walkthrough

1. Choose a scenario and reproducible seed, then press **Apply & restart**.
2. Select a speed and press **Start**, or use **Step +5m** for exact paused progression.
3. Watch workload observations, prediction cycles, deficits, safe surplus capacity, reservations, and contracts update together.
4. Open **Predictions** to inspect the four future horizons and confidence-aware safe commitments.
5. Inject a spike, drop, or capacity failure for a selected provider and observe risk, renegotiation, or emergency recovery events.
6. Use **Same seed** to return to Day 1 at 08:00 and reproduce the same stochastic workload and event schedule.

At 100×, one simulated hour takes about 36 real seconds. Wall-clock speed does not change the deterministic outcome of a seeded run.

The **Phase 1 manual lab** remains available for the original fixed teaching sequence: generate predictions, run matching, create a contract, revise the prediction, activate and complete contracts, or simulate a provider failure.

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

Existing databases upgraded during Phase 4 may retain unused compatibility columns. Phase 3 does not expose or depend on them; they remain mapped only so rollback can operate safely against those databases without destructive schema changes.
