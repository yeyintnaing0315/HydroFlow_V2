"""Pytest uses a temporary SQLite file for the operational schema.

DATABASE_URL is set before the app is imported so collection never opens
PostgreSQL and never writes the repository hydroflow.db.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

_PYTEST_DIR = Path(tempfile.mkdtemp(prefix="hydroflow-v2-pytest-"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_PYTEST_DIR / 'operational.sqlite').as_posix()}"
os.environ["INVENTORY_DATABASE_URL"] = os.environ["DATABASE_URL"]
os.environ["HYDRO_FEATURES_CACHE"] = str(_PYTEST_DIR / "hydro_features.sqlite")
os.environ["ROAD_CACHE"] = str(_PYTEST_DIR / "road_cache.sqlite")
# Planner tests stay on the ratio fallback. A trained artifact must not change rice totals.
os.environ["ALLOCATION_MODEL_PATH"] = str(_PYTEST_DIR / "missing-allocation.joblib")
os.environ["ALLOCATION_METADATA_PATH"] = str(_PYTEST_DIR / "missing-allocation.json")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app


@pytest.fixture()
def session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as value:
        yield value
    Base.metadata.drop_all(engine)


@pytest.fixture()
def client(session: Session):
    app.dependency_overrides[get_db] = lambda: session
    with TestClient(app) as value:
        yield value
    app.dependency_overrides.clear()
