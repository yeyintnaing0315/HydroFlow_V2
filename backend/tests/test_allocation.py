import asyncio
import time
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db, get_inventory_db
from app.main import app
from app.schemas.api import AllocationPlanRequest
from app.services import allocation, help_prediction
from app.services.inventory import add_region_stock, seed_catalog, seed_regions


@pytest.fixture()
def inventory_session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed_catalog(session)
        seed_regions(session)
        add_region_stock(
            session,
            region="east",
            category_code="foods",
            item_code="rice",
            quantity=100,
            entry_mode="manual",
            direction="in",
        )
        add_region_stock(
            session,
            region="east",
            category_code="utilities",
            item_code="blanket",
            quantity=50,
            entry_mode="manual",
            direction="in",
        )
        session.commit()
        yield session
    Base.metadata.drop_all(engine)


@pytest.fixture()
def geo_session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)


def _sample_townships():
    return [
        allocation.TownshipCatalog("bago", "Bago", 17.336, 96.481),
        allocation.TownshipCatalog("taungoo", "Taungoo", 18.937, 96.433),
    ]


def _help_score(*, people: int, priority: str) -> dict:
    households = max(1, people // 4)
    return {
        "help_probability": 0.6,
        "predicted_help": True,
        "expected_affected_people": people,
        "expected_households": households,
        "assistance_priority": priority,
        "shelter_kits": households,
        "food_rations_3d": people * 3,
        "drinking_water_liters_3d": people * 9,
        "model_version": "flood-help-v2",
    }


def test_allocation_plan_ranks_townships_and_assigns_routes(
    monkeypatch: pytest.MonkeyPatch,
    geo_session: Session,
    inventory_session: Session,
) -> None:
    async def fake_help(township: allocation.TownshipCatalog, _day: date):
        if township.id == "bago":
            return _help_score(people=120, priority="high")
        return _help_score(people=8000, priority="severe")

    monkeypatch.setattr(allocation, "_iter_townships", lambda _s, _ids: _sample_townships())

    monkeypatch.setattr(allocation, "_help_for_township", fake_help)
    monkeypatch.setattr(help_prediction, "load_help_model", lambda: ({}, {}))
    async def _no_osrm(_pts):
        return None

    monkeypatch.setattr(allocation.osrm, "driving_path", _no_osrm)

    request = AllocationPlanRequest(date=date(2026, 10, 15), warehouse_region="east")
    plan = asyncio.run(build_allocation_plan(geo_session, inventory_session, request))

    assert len(plan.rows) == 2
    assert plan.rows[0].township_name == "Taungoo"
    assert plan.rows[1].township_name == "Bago"
    assert plan.rows[0].route_id in {"Route A", "Route B", "Route C"}
    assert plan.totals.affected_population == 1120
    assert plan.shortages
    assert plan.routes
    assert plan.model_version.endswith("allocation-rules-fallback") or plan.model_version.endswith("allocation-v3")
    codes = {(item.category_code, item.item_code) for row in plan.rows for item in row.line_items}
    assert ("foods", "rice") in codes
    assert ("utilities", "blanket") in codes
    assert ("clothing", "tshirt") in codes
    assert ("kitchenware", "water_dipper") in codes
    assert all(category not in {"utility", "clothes"} for category, _item in codes)


def test_allocation_api(client: TestClient, monkeypatch: pytest.MonkeyPatch, inventory_session: Session) -> None:
    async def fake_help(township: allocation.TownshipCatalog, _day: date):
        return _help_score(people=200, priority="high")

    monkeypatch.setattr(allocation, "_iter_townships", lambda _s, _ids: _sample_townships()[:1])
    monkeypatch.setattr(allocation, "_help_for_township", fake_help)
    monkeypatch.setattr(help_prediction, "load_help_model", lambda: ({}, {}))
    async def _no_osrm(_pts):
        return None

    monkeypatch.setattr(allocation.osrm, "driving_path", _no_osrm)

    app.dependency_overrides[get_inventory_db] = lambda: inventory_session
    response = client.post(
        "/allocation/plan",
        json={"date": "2026-10-15", "warehouse_region": "east", "min_priority": "moderate"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["rows"][0]["township_name"] == "Bago"
    assert "plan_id" in body
    assert body["rows"][0]["requested_total"] == sum(item["requested"] for item in body["rows"][0]["line_items"])
    assert body["rows"][0]["allocated_total"] == sum(item["allocated"] for item in body["rows"][0]["line_items"])
    assert body["rows"][0]["flood_probability"] is None
    detail = client.get(f"/allocation/plans/{body['plan_id']}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["rows"][0]["township_name"] == "Bago"
    assert detail.json()["rows"][0]["requested_total"] == body["rows"][0]["requested_total"]
    assert detail.json()["planning_date"] == "2026-10-15"
    app.dependency_overrides.pop(get_inventory_db, None)


def test_allocation_dispatch_reduces_stock(inventory_session: Session) -> None:
    app.dependency_overrides[get_inventory_db] = lambda: inventory_session
    with TestClient(app) as client:
        response = client.post(
            "/allocation/dispatch",
            json={
                "warehouse_region": "east",
                "lines": [
                    {
                        "category_code": "foods",
                        "item_code": "rice",
                        "quantity": 10,
                        "destination": "Bago",
                    }
                ],
            },
        )
    app.dependency_overrides.pop(get_inventory_db, None)
    assert response.status_code == 200
    rice = next(
        item
        for klass in response.json()["classes"]
        if klass["code"] == "foods"
        for item in klass["items"]
        if item["code"] == "rice"
    )
    assert rice["quantity"] == 90.0


def build_allocation_plan(geo_session, inventory_session, request):
    return allocation.build_allocation_plan(geo_session, inventory_session, request)


def test_plan_lists_unverified_stores_and_does_not_spend_stock(
    monkeypatch: pytest.MonkeyPatch,
    geo_session: Session,
    inventory_session: Session,
) -> None:
    async def fake_help(township: allocation.TownshipCatalog, _day: date):
        return _help_score(people=40, priority="high")

    monkeypatch.setattr(allocation, "_iter_townships", lambda _s, _ids: _sample_townships()[:1])
    monkeypatch.setattr(allocation, "_help_for_township", fake_help)
    async def _no_osrm(_pts):
        return None

    monkeypatch.setattr(allocation.osrm, "driving_path", _no_osrm)

    request = AllocationPlanRequest(date=date(2026, 10, 15), warehouse_region="east", commit_inventory=True)
    plan = asyncio.run(build_allocation_plan(geo_session, inventory_session, request))

    assert plan.status == "draft"
    assert [store.region for store in plan.unverified_stores] == ["east"]
    assert all(item.allocated == 0 for row in plan.rows for item in row.line_items)
    rice = next(
        item
        for klass in allocation.region_snapshot(inventory_session, "east")["classes"]
        if klass["code"] == "foods"
        for item in klass["items"]
        if item["code"] == "rice"
    )
    assert rice["quantity"] == 100.0


def test_confirm_deducts_stock_only_after_verification(
    monkeypatch: pytest.MonkeyPatch,
    geo_session: Session,
    inventory_session: Session,
) -> None:
    from datetime import datetime, timezone

    from sqlalchemy import select

    from app.models import AllocationLine, AllocationPlan, StockMovement
    from app.services.inventory import store_for_region

    async def fake_help(_township: allocation.TownshipCatalog, _day: date):
        return _help_score(people=80, priority="severe")

    monkeypatch.setattr(allocation, "_iter_townships", lambda _s, _ids: _sample_townships()[:1])
    monkeypatch.setattr(allocation, "_help_for_township", fake_help)
    async def _no_osrm(_pts):
        return [{"latitude": 17.3, "longitude": 96.4}, {"latitude": 18.9, "longitude": 96.4}]

    monkeypatch.setattr(allocation.osrm, "driving_path", _no_osrm)
    store = store_for_region(inventory_session, "east")
    store.verified_at = datetime.now(timezone.utc)
    inventory_session.commit()

    request = AllocationPlanRequest(date=date(2026, 10, 15), warehouse_region="east")
    plan = asyncio.run(build_allocation_plan(geo_session, inventory_session, request))
    assert plan.unverified_stores == []
    assert plan.rows[0].township_name == "Bago"
    rice_before = next(
        item
        for klass in allocation.region_snapshot(inventory_session, "east")["classes"]
        if klass["code"] == "foods"
        for item in klass["items"]
        if item["code"] == "rice"
    )
    assert rice_before["quantity"] == 100.0
    saved = geo_session.get(AllocationPlan, int(plan.plan_id))
    assert saved is not None and saved.status == "draft"
    lines = list(geo_session.scalars(select(AllocationLine).where(AllocationLine.plan_id == saved.id)))
    rice_line = next(line for line in lines if line.item_code == "rice" and line.township_id == "bago")
    assert float(rice_line.requested) == 80
    assert float(rice_line.allocated) == 80

    result = allocation.confirm_allocation_plan(geo_session, inventory_session, saved.id)
    assert result.status == "confirmed"
    rice_after = next(
        item
        for klass in allocation.region_snapshot(inventory_session, "east")["classes"]
        if klass["code"] == "foods"
        for item in klass["items"]
        if item["code"] == "rice"
    )
    assert rice_after["quantity"] == 20.0
    movement = inventory_session.scalar(
        select(StockMovement).where(StockMovement.allocation_line_id == rice_line.id)
    )
    assert movement is not None
    assert movement.direction == "out"
    assert float(movement.quantity) == 80


def test_saved_plan_points_at_prediction_run(
    monkeypatch: pytest.MonkeyPatch,
    geo_session: Session,
    inventory_session: Session,
) -> None:
    from app.models import PredictionRun, TownshipForecast

    async def fake_help(_township: allocation.TownshipCatalog, _day: date):
        return _help_score(people=12, priority="high")

    monkeypatch.setattr(allocation, "_iter_townships", lambda _s, _ids: _sample_townships()[:1])
    monkeypatch.setattr(allocation, "_help_for_township", fake_help)
    async def _no_osrm(_pts):
        return None

    monkeypatch.setattr(allocation.osrm, "driving_path", _no_osrm)
    run = PredictionRun(
        as_of=date(2026, 10, 15),
        model_version="flood-v2",
        feature_version="features-v2",
        status="ready",
    )
    geo_session.add(run)
    geo_session.flush()
    geo_session.add(
        TownshipForecast(
            run_id=run.id,
            township_id="bago",
            target_date=date(2026, 10, 15),
            lead_days=0,
            probability=0.82,
            risk_band="high",
            feature_version="features-v2",
            features={},
        )
    )
    geo_session.flush()

    request = AllocationPlanRequest(date=date(2026, 10, 15), warehouse_region="east")
    plan = asyncio.run(build_allocation_plan(geo_session, inventory_session, request))
    assert plan.prediction_run_id == run.id
    assert plan.routes
    assert plan.routes[0].routing_method == "flood_aware_blocked"


def test_jrc_floodplain_blocks_corridor_without_osrm(
    monkeypatch: pytest.MonkeyPatch,
    geo_session: Session,
) -> None:
    from app.models import TownshipStaticFeatures
    from app.services.flood_routing import route_delivery

    called = {"count": 0}

    async def _osrm(_pts):
        called["count"] += 1
        return [{"latitude": 1.0, "longitude": 1.0}, {"latitude": 2.0, "longitude": 2.0}]

    monkeypatch.setattr("app.services.osrm.driving_path", _osrm)
    geo_session.add(
        TownshipStaticFeatures(
            township_id="bago",
            jrc_rp10_depth_m=0.8,
            feature_version="static-v1",
            features={},
        )
    )
    geo_session.flush()
    corridor = asyncio.run(
        route_delivery(
            geo_session,
            origin_id="depot:east",
            stops=[("bago", 17.336, 96.481)],
            nodes=[
                ("depot:east", 17.335, 96.481),
                ("bago", 17.336, 96.481),
            ],
            planning_date=date(2026, 10, 15),
        )
    )
    assert corridor.routing_method == "flood_aware_blocked"
    assert called["count"] == 0
    assert corridor.blocked_segments


def test_plan_uses_straight_line_when_osrm_hangs(
    monkeypatch: pytest.MonkeyPatch,
    geo_session: Session,
    inventory_session: Session,
) -> None:
    async def fake_help(township: allocation.TownshipCatalog, _day: date):
        return _help_score(people=90, priority="high")

    async def slow_osrm(_points, timeout=None):
        del timeout
        await asyncio.sleep(30)
        return [{"latitude": 17.3, "longitude": 96.5}, {"latitude": 18.9, "longitude": 96.4}]

    monkeypatch.setattr(allocation, "_iter_townships", lambda _session, _ids: _sample_townships()[:1])
    monkeypatch.setattr(allocation, "_help_for_township", fake_help)
    monkeypatch.setattr(allocation.osrm, "driving_path", slow_osrm)

    request = AllocationPlanRequest(date=date(2026, 10, 27), warehouse_region="east")
    started = time.perf_counter()
    plan = asyncio.run(build_allocation_plan(geo_session, inventory_session, request))
    elapsed = time.perf_counter() - started

    assert elapsed < 12, elapsed
    assert plan.status == "draft"
    assert plan.routes
    assert plan.routes[0].routing_method == "straight_line_fallback"
    assert len(plan.routes[0].path) >= 2
    rice = next(
        item
        for klass in allocation.region_snapshot(inventory_session, "east")["classes"]
        if klass["code"] == "foods"
        for item in klass["items"]
        if item["code"] == "rice"
    )
    assert rice["quantity"] == 100.0


def test_plan_row_keeps_forecast_measurements(
    monkeypatch: pytest.MonkeyPatch,
    geo_session: Session,
    inventory_session: Session,
) -> None:
    from app.models import PredictionRun, TownshipForecast

    async def fake_help(township: allocation.TownshipCatalog, _day: date):
        return _help_score(people=30, priority="high")

    monkeypatch.setattr(allocation, "_iter_townships", lambda _s, _ids: _sample_townships()[:1])
    monkeypatch.setattr(allocation, "_help_for_township", fake_help)

    async def _no_osrm(_pts):
        return None

    monkeypatch.setattr(allocation.osrm, "driving_path", _no_osrm)
    run = PredictionRun(
        as_of=date(2026, 10, 15),
        model_version="v2",
        feature_version="static-1",
        status="succeeded",
    )
    geo_session.add(run)
    geo_session.flush()
    geo_session.add(
        TownshipForecast(
            run_id=run.id,
            township_id="bago",
            target_date=date(2026, 10, 15),
            lead_days=0,
            probability=0.82,
            risk_band="high",
            rainfall_mm=12.5,
            discharge_m3_s=3.4,
            feature_version="static-1",
        )
    )
    geo_session.flush()

    request = AllocationPlanRequest(date=date(2026, 10, 15), warehouse_region="east")
    plan = asyncio.run(build_allocation_plan(geo_session, inventory_session, request))
    row = plan.rows[0]
    assert row.flood_probability == pytest.approx(0.82)
    assert row.risk_band == "high"
    assert row.rainfall_mm == pytest.approx(12.5)
    assert row.discharge_m3_s == pytest.approx(3.4)
    assert row.requested_total > 0


def test_confirm_rejects_when_stock_dropped(
    monkeypatch: pytest.MonkeyPatch,
    geo_session: Session,
    inventory_session: Session,
) -> None:
    from datetime import datetime, timezone

    from app.models import AllocationPlan
    from app.services.inventory import store_for_region

    async def fake_help(_township: allocation.TownshipCatalog, _day: date):
        return _help_score(people=80, priority="severe")

    monkeypatch.setattr(allocation, "_iter_townships", lambda _s, _ids: _sample_townships()[:1])
    monkeypatch.setattr(allocation, "_help_for_township", fake_help)

    async def _no_osrm(_pts):
        return None

    monkeypatch.setattr(allocation.osrm, "driving_path", _no_osrm)
    store = store_for_region(inventory_session, "east")
    store.verified_at = datetime.now(timezone.utc)
    inventory_session.commit()
    request = AllocationPlanRequest(date=date(2026, 10, 15), warehouse_region="east")
    plan = asyncio.run(build_allocation_plan(geo_session, inventory_session, request))
    add_region_stock(
        inventory_session,
        region="east",
        category_code="foods",
        item_code="rice",
        quantity=90,
        entry_mode="manual",
        direction="out",
    )
    inventory_session.commit()

    with pytest.raises(allocation.AllocationStateError, match="no longer covers"):
        allocation.confirm_allocation_plan(geo_session, inventory_session, int(plan.plan_id))

    saved = geo_session.get(AllocationPlan, int(plan.plan_id))
    assert saved is not None and saved.status == "draft"
    rice = next(
        item
        for klass in allocation.region_snapshot(inventory_session, "east")["classes"]
        if klass["code"] == "foods"
        for item in klass["items"]
        if item["code"] == "rice"
    )
    assert rice["quantity"] == 10.0
