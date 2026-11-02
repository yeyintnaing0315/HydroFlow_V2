from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.allocation import router as allocation_router
from app.api.health import router as health_router
from app.api.hydrology import router as hydrology_router
from app.api.inventory import router as inventory_router
from app.api.operations import router as operations_router
from app.api.prediction import router as prediction_router
from app.api.simulation import router as simulation_router
from app.db import InventorySession, init_operational_database
from app.services.inventory import ensure_demo_stock


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_operational_database()
    with InventorySession() as inventory_session:
        try:
            ensure_demo_stock(inventory_session)
            inventory_session.commit()
        except Exception:
            inventory_session.rollback()
            raise
    yield


app = FastAPI(
    title="HydroFlow V2 API",
    version="0.1.0",
    description="Academic flood-risk prototype; not for operational warnings.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health_router)
app.include_router(hydrology_router)
app.include_router(operations_router)
app.include_router(prediction_router)
app.include_router(allocation_router)
app.include_router(simulation_router)
app.include_router(inventory_router)
