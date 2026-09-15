# Confidence-Aware Predictive Cloud Bartering

Phase 4 academic prototype for a seeded stochastic cloud federation. It combines noisy workloads and capacity failures with strict-history workload forecasting, uncertainty-aware predictive bartering, emergency recovery, model evaluation, and reproducible strategy experiments.

## What is included

- FastAPI + SQLAlchemy REST backend with a PostgreSQL-ready schema
- React + Vite dashboard with provider, prediction, marketplace, contract, reputation, and event-log views
- Automatically seeded Cloud A–D demo data
- Reproducible seeded runs plus a fresh-random-seed mode
- Persistent credit, collateral, reputation, renegotiation, and system-event histories
- Independent stochastic workload, event, failure, forecast, marketplace, and emergency-recovery modules
- Start/pause/resume/reset/step simulation clock with 1×–100× speed control
- Stable, Normal, Volatile, Failure Test, and Stress Test presets
- Provider personalities with correlated noise, office peaks, consumer bursts, batch demand, and different volatility/confidence characteristics
- Seeded workload spikes and drops, abnormal events, partial/full capacity loss, named failure causes, and automatic recovery
- Automatic 30-minute prediction cycles at +15m, +30m, +1h, +2h, and +4h horizons
- A common forecasting interface with Naive, weighted Moving Average, Linear Trend, and additive Holt-Winters models
- Independent CPU/RAM forecasts, configurable rolling training windows, safe short-history fallback, and automatic per-provider model selection
- Shadow-model evaluation that never influences matching unless the model is selected for decisions
- Forecasts based only on observations available at forecast time; future generated events stay hidden
- Uncertainty/error/volatility/horizon-derived confidence, MAE, RMSE, MAPE, bias, failure attribution, and confidence calibration
- Automatic multi-provider matching, future-capacity reservation, lifecycle, risk monitoring, renegotiation, and emergency reactive barter
- Reactive Only, Predictive, and Confidence-Aware Predictive strategies with uncertainty-safe commitments and confidence-tier collateral
- Live model, horizon, revision, predictive-vs-reactive, shortage, reaction-time, efficiency, resilience, credit, and run-comparison analytics
- Persisted experiment configuration, same-seed comparison, descriptive statistics, and CSV/JSON export
- Manual spike/drop/failure injection for demos and experiments
- Provider drill-down monitoring pages and a filterable simulation event timeline

## Run locally

Prerequisites: Python 3.11+, Node 20+, and Docker (or an existing PostgreSQL 14+ server).

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

The database tables and demo providers are created automatically on API startup. The container publishes PostgreSQL on host port `55432` so it can coexist with a local PostgreSQL installation on the standard `5432` port. To run the backend without Docker for quick testing, set `DATABASE_URL=sqlite:///./cloud_barter.db` in `backend/.env`.

## Phase 4 forecasting experiment

1. Select a scenario, seed, decision model (or Auto), shadow models, rolling window, and strategy, then press **Apply & restart**.
2. Choose `100×` and press **Start**, or step forward while paused for repeatable experiments.
3. Watch baseline curves become noisy observed workloads. Event markers identify spikes, drops, failures, recoveries, contract risk, renegotiation, and emergency actions.
4. Use the injection controls to trigger a critical spike or failure on a chosen provider.
5. Open **Forecasting** to compare actual demand with forecasts, inspect errors by time/model/horizon, and track forecast revisions.
6. Repeat the same seed under **Reactive Only**, **Predictive**, and **Confidence-Aware Predictive**. Use **Experiments** and **Comparison** for the saved run matrix, statistical summary, and exports.

At 100×, one simulated hour takes about 36 real seconds. **Same seed** returns to Day 1 at 08:00:00 and reproduces the same minute-level observations and event schedule. **Random seed** starts a fresh stochastic run. Historical run summaries remain available.

The forecasting layer intentionally uses transparent, lightweight statistical models. It does not use future simulator state during training or inference, and it does not add heavy LSTM, Prophet, reinforcement-learning, or external dataset dependencies.

## Phase 1 manual walkthrough

Use the controls in order:

1. **Reset demo** — restores the four providers and a clean ledger.
2. **Generate predictions** — creates Cloud A's deficit and B/C/D surplus forecasts.
3. **Run matching** — ranks possible suppliers and explains the score.
4. **Create best contract** — schedules B → A and locks B's collateral.
5. **Re-evaluate predictions** — reduces B's forecast and splits the agreement into B → A and C → A replacement contracts.
6. **Start contracts** — activates all scheduled replacement contracts.
7. **Complete contracts** — settles credits, releases collateral, measures forecast error, and updates scores.

You can also simulate a provider failure against the next active or scheduled contract.

## Architecture

```text
backend/app/
  forecasting/        model interface, four forecasters, confidence, selection, evaluation
  models/             SQLAlchemy entities and status enums
  routers/            REST transport only
  services/           matching, contracts, credits, reputation, renegotiation
  simulation/         clock, seeded RNG, scenarios, workloads, events, failures, and run history
frontend/src/
  components/         reusable dashboard components
  pages/              workflow views
```

Business services depend on persisted predictions and resource states, not on future simulator knowledge. The random manager is stateless and keyed by seed, provider, and simulated minute, so wall-clock speed does not change a run's outcome.

## Configuration

The Phase 1 economic formulas and Phase 4 forecasting/risk defaults remain centralized in `backend/app/config.py`. Phase 3 scenario probabilities live in `backend/app/simulation/scenario_presets.py`, while provider behavior lives in `workload_profiles.py`.

The preserved Phase 1 formulas include:

- safe commitment confidence multiplier
- collateral rate
- matching score weights
- SLA/reliability success and failure adjustments
- contribution score weights

## Tests

```powershell
cd backend
pytest
```

The integration suite verifies the original Phase 1 contract workflow, Phase 2/3 simulation behavior, exact same-seed reproduction, all four Phase 4 models and five horizons, no-future-data boundaries, uncertainty output, decision-vs-shadow isolation, strategy comparison, and CSV/JSON experiment export.
