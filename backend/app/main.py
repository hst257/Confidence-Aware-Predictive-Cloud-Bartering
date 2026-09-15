import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .database import SessionLocal, init_database
from .routers.api import router
from .services.demo_service import seed_if_empty
from .simulation.engine import run_engine_loop
from .simulation.mutation_lock import simulation_mutation
from .simulation.simulation_state import get_or_create_state


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_database()
    with SessionLocal() as db:
        with simulation_mutation(db):
            seed_if_empty(db)
            get_or_create_state(db)
            db.commit()
    engine_task = asyncio.create_task(run_engine_loop(), name="phase3-stochastic-simulation-engine")
    try:
        yield
    finally:
        engine_task.cancel()
        with suppress(asyncio.CancelledError):
            await engine_task


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version="3.0.0-phase3",
        description="Seeded stochastic cloud simulation with simple predictive and emergency resource bartering.",
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(router)
    return application


app = create_app()
