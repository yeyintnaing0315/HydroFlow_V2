"""Operational schema, PostgreSQL failure, and SQLite cache isolation."""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.cache import insert_travel_edge, list_daily_observations, list_travel_edges, upsert_daily_observation
from app.db import (
    Base,
    OperationalDatabaseError,
    SessionLocal,
    create_tables,
    ensure_operational_connection,
    get_db,
    get_inventory_db,
    inventory_shares_operational_db,
)
from app.models import AllocationPlan, Location, PredictionRun, TownshipForecast


def test_postgres_down_does_not_fall_back_to_sqlite(monkeypatch, tmp_path: Path) -> None:
    created: list[str] = []
    real_create_engine = create_engine

    def spy(url, *args, **kwargs):
        created.append(str(url))
        if str(url).startswith("sqlite"):
            raise AssertionError(f"operational init opened SQLite: {url}")
        return real_create_engine(url, *args, **kwargs)

    monkeypatch.setattr("app.db.create_engine", spy)
    url = "postgresql+psycopg://hydroflow:secret-token@127.0.0.1:1/hydroflow"
    with pytest.raises(OperationalDatabaseError, match="SQLite") as caught:
        ensure_operational_connection(url)
    message = str(caught.value)
    assert "PostgreSQL" in message
    assert "secret-token" not in message
    assert created
    assert all(item.startswith("postgresql") for item in created)
    assert not (tmp_path / "hydroflow.db").exists()


def test_shared_inventory_session_reuses_operational_connection() -> None:
    assert inventory_shares_operational_db()
    geo_generator = get_db()
    geo = next(geo_generator)
    inventory = next(get_inventory_db(geo))
    assert inventory is geo
    geo_generator.close()


def test_operational_session_rolls_back_on_error() -> None:
    create_tables()
    generator = get_db()
    session = next(generator)
    session.add(Location(name="rollback-probe", latitude=1.0, longitude=2.0))
    session.flush()
    with pytest.raises(RuntimeError, match="boom"):
        generator.throw(RuntimeError("boom"))
    with SessionLocal() as check:
        found = check.scalar(select(Location).where(Location.name == "rollback-probe"))
    assert found is None


def test_cache_write_does_not_commit_operational_session(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HYDRO_FEATURES_CACHE", str(tmp_path / "hydro_features.sqlite"))
    monkeypatch.setenv("ROAD_CACHE", str(tmp_path / "road_cache.sqlite"))
    operational = create_engine(
        f"sqlite:///{(tmp_path / 'operational.sqlite').as_posix()}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(operational)
    with Session(operational) as session:
        session.add(Location(name="cache-probe", latitude=17.335, longitude=96.481))
        session.flush()
        upsert_daily_observation(
            township_id="bago",
            observed_on=date(2026, 10, 15),
            source="open-meteo",
            payload={"precipitation_mm": 12.5},
        )
        insert_travel_edge(
            from_id="depot-east",
            to_id="bago",
            distance_m=1200.0,
            duration_s=180.0,
            crosses_floodplain=False,
            geometry={"type": "LineString", "coordinates": [[96.481, 17.335], [96.5, 17.34]]},
        )
        session.rollback()
    with Session(operational) as check:
        assert check.scalar(select(Location).where(Location.name == "cache-probe")) is None
    observations = list_daily_observations()
    assert observations == [
        {
            "township_id": "bago",
            "date": date(2026, 10, 15),
            "source": "open-meteo",
            "payload": {"precipitation_mm": 12.5},
            "fetched_at": observations[0]["fetched_at"],
        }
    ]
    assert list_travel_edges()[0]["from_id"] == "depot-east"
    assert list_travel_edges()[0]["crosses_floodplain"] is False
    operational.dispose()


def test_forecast_identity_and_plan_status() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    names = set(inspect(engine).get_table_names())
    assert "bago_east_balances" not in names
    assert "stores" in names
    assert "township_forecasts" in names
    with Session(engine) as session:
        run = PredictionRun(
            as_of=date(2026, 10, 27),
            model_version="v2",
            feature_version="static-1",
            status="succeeded",
        )
        session.add(run)
        session.flush()
        forecast = TownshipForecast(
            run_id=run.id,
            township_id="bago",
            target_date=date(2026, 10, 28),
            lead_days=1,
            probability=0.4,
            risk_band="moderate",
            feature_version="static-1",
        )
        session.add(forecast)
        session.commit()
        session.add(
            TownshipForecast(
                run_id=run.id,
                township_id="bago",
                target_date=date(2026, 10, 28),
                lead_days=1,
                probability=0.9,
                risk_band="high",
                feature_version="static-1",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        session.add(AllocationPlan(status="published"))
        with pytest.raises(IntegrityError):
            session.commit()
    engine.dispose()


def test_ensure_model_columns_adds_missing_plan_context(tmp_path: Path) -> None:
    legacy = create_engine(
        f"sqlite:///{(tmp_path / 'legacy.sqlite').as_posix()}",
        connect_args={"check_same_thread": False},
    )
    with legacy.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE allocation_plans ("
                "id INTEGER PRIMARY KEY, "
                "prediction_run_id INTEGER, "
                "created_at DATETIME NOT NULL, "
                "status VARCHAR(20) NOT NULL)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO allocation_plans (id, prediction_run_id, created_at, status) "
                "VALUES (1, NULL, '2026-10-31 11:24:04', 'draft')"
            )
        )
    from app.db import _ensure_model_columns

    _ensure_model_columns(legacy)
    columns = {column["name"] for column in inspect(legacy).get_columns("allocation_plans")}
    assert "plan_context" in columns
    _ensure_model_columns(legacy)
    with Session(legacy) as session:
        plan = session.get(AllocationPlan, 1)
        assert plan is not None
        assert plan.plan_context is None
        assert plan.status == "draft"
    legacy.dispose()


def test_alembic_upgrade_creates_sqlite_operational_schema(tmp_path: Path) -> None:
    database = tmp_path / "migrated.sqlite"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{database.as_posix()}"
    root = Path(__file__).resolve().parents[2]
    env["PYTHONPATH"] = str(root / "backend")
    completed = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr + completed.stdout
    engine = create_engine(env["DATABASE_URL"])
    names = set(inspect(engine).get_table_names())
    assert {
        "stores",
        "stock_balances",
        "stock_movements",
        "township_static_features",
        "prediction_runs",
        "township_forecasts",
        "flood_labels",
        "allocation_plans",
        "allocation_lines",
        "delivery_routes",
        "route_stops",
        "township_route_options",
        "detection_sessions",
        "detection_objects",
    } <= names
    for legacy in (
        "bago_east_balances",
        "bago_west_balances",
        "bago_east_movements",
        "bago_west_movements",
    ):
        assert legacy not in names
    with engine.connect() as connection:
        revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
        stores = connection.execute(
            text("SELECT region, name, latitude, longitude FROM stores ORDER BY region")
        ).all()
        balance_count = connection.execute(text("SELECT COUNT(*) FROM stock_balances")).scalar()
    assert revision == "20261031_0010"
    assert [(row.region, row.name) for row in stores] == [
        ("east", "Bago depot east"),
        ("west", "Pyay depot west"),
    ]
    assert stores[0].latitude == pytest.approx(17.335)
    assert stores[0].longitude == pytest.approx(96.481)
    assert stores[1].latitude == pytest.approx(18.817)
    assert stores[1].longitude == pytest.approx(95.217)
    assert balance_count == 38
    engine.dispose()
