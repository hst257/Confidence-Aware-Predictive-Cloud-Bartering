# Repository Guidelines

Whatever action you can do yourself, Please do yourself, this includes starting apps and verification

## Project Structure & Module Organization

The repository contains a FastAPI backend and a React/Vite frontend.

- `backend/app/main.py` creates the API application; `routers/api.py` defines REST endpoints.
- `backend/app/models/` contains SQLAlchemy entities and enums.
- `backend/app/services/` owns marketplace logic: matching, contracts, credits, reputation, renegotiation, emergency barter, and analytics.
- `backend/app/simulation/` owns the deterministic clock, seeded workloads, events, failures, predictions, and run state. Keep simulation generation separate from business services.
- `backend/tests/test_demo_workflow.py` contains end-to-end pytest coverage.
- `frontend/src/components/` contains reusable UI pieces; `frontend/src/pages/` contains workflow screens. Shared API contracts live in `types.ts` and requests in `api.ts`.

## Build, Test, and Development Commands

```powershell
docker compose up -d postgres          # Start PostgreSQL on port 55432
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload          # API at localhost:8000
```

Use `DATABASE_URL=sqlite:///./cloud_barter.db` for a Docker-free local database.

```powershell
cd frontend
npm install
npm run dev                            # Vite UI at localhost:5173
npm run build                          # Type-check and production build
cd ..\backend
.venv\Scripts\python.exe -m pytest -q # Backend integration suite
```

## Coding Style & Naming Conventions

Use Phosphor icons from `@phosphor-icons/react` for all frontend icons. Use the `Icon`-suffixed named exports with regular weight by default; keep existing icon sizes and accessible labels. Do not introduce Lucide or another icon library. Follow the visual tokens in `DESIGN.md`, preserving the current structure, layout, and animations unless the user explicitly requests changes.

Use four spaces in Python and two spaces in TypeScript/TSX. Follow `snake_case` for Python functions/modules, `PascalCase` for React components and TypeScript types, and `camelCase` for frontend variables. Keep API handlers thin; put domain behavior in services and stochastic behavior in `simulation/`. No formatter or linter is configured, so match surrounding style and run the build/tests before committing.

## Testing Guidelines

Pytest is the backend test framework. Name tests `test_<behavior>` and prefer API-level assertions through `TestClient`. Seed stochastic scenarios explicitly so failures are reproducible. There is no numeric coverage threshold; every behavior change should include a focused regression test. Frontend changes must pass `npm run build` and should be checked in the browser for console errors and responsive layout issues.

## Commit & Pull Request Guidelines

Recent history uses imperative, scoped messages such as `restore: stable phase 3 stochastic simulation` and `backup: phase 4 unstable state before rollback`. Follow `<scope>: <concise outcome>`. Pull requests should explain the user-visible behavior, affected API/data contracts, verification commands, and any schema compatibility considerations. Link relevant issues and include screenshots for UI changes. Never commit `.env`, database files, virtual environments, `node_modules`, or generated `dist/` output.
