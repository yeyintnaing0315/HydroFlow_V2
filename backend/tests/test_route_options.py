import asyncio
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import TownshipRouteOption
from app.schemas.api import AllocationPlanRequest
from app.services import allocation
from app.services.flood_routing import DeliveryCorridor
from app.services.inventory import add_region_stock, seed_catalog, seed_regions, store_for_region

from tests.test_allocation import _boost_depot_stock
from app.services.route_options import compare_township_routes, select_township_route


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
        store = store_for_region(session, "east")
        store.verified_at = datetime.now(timezone.utc)
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


def _sample():
    return [allocation.TownshipCatalog("bago", "Bago", 17.336, 96.481)]


def _help_score() -> dict:
    return {
        "help_probability": 0.6,
        "predicted_help": True,
        "expected_affected_people": 40,
        "expected_households": 10,
        "assistance_priority": "high",
        "shelter_kits": 10,
        "food_rations_3d": 120,
        "drinking_water_liters_3d": 360,
        "model_version": "flood-help-v2",
    }


def _road(duration: float, longitude: float) -> dict:
    return {
        "path": [
            {"latitude": 17.335, "longitude": 96.481},
            {"latitude": 17.4, "longitude": longitude},
            {"latitude": 17.336, "longitude": 96.481},
            {"latitude": 17.335, "longitude": 96.481},
        ],
        "distance_m": duration * 10,
        "duration_s": duration,
    }


async def _plan(geo_session: Session, inventory_session: Session, monkeypatch: pytest.MonkeyPatch):
    async def fake_help(_township, _day):
        return _help_score()

    async def _no_osrm(_pts):
        return None

    monkeypatch.setattr(allocation, "_iter_townships", lambda _s, _ids: _sample())
    monkeypatch.setattr(allocation, "_help_for_township", fake_help)
    monkeypatch.setattr(allocation.osrm, "driving_route", _no_osrm)
    _boost_depot_stock(inventory_session, "east")
    return await allocation.build_allocation_plan(
        geo_session,
        inventory_session,
        AllocationPlanRequest(date=date(2026, 10, 15), warehouse_region="east"),
    )


def test_route_alternatives_are_capped_and_ranked(
    monkeypatch: pytest.MonkeyPatch,
    geo_session: Session,
    inventory_session: Session,
) -> None:
    plan = asyncio.run(_plan(geo_session, inventory_session, monkeypatch))

    async def roads(_points, timeout=None, alternatives=2):
        del timeout, alternatives
        return [_road(30, 96.5), _road(10, 96.6), _road(20, 96.7), _road(40, 96.8)]

    async def graph(*_args, **_kwargs):
        return DeliveryCorridor(
            ordered_stop_ids=["bago"],
            path=[
                {"latitude": 17.335, "longitude": 96.481},
                {"latitude": 18.2, "longitude": 96.2},
                {"latitude": 17.336, "longitude": 96.481},
            ],
            routing_method="flood_aware_graph",
            blocked_segments=[],
            distance_m=50000,
            duration_s=4000,
        )

    monkeypatch.setattr("app.services.route_options.osrm.driving_alternatives", roads)
    monkeypatch.setattr("app.services.route_options.route_delivery", graph)
    compared = asyncio.run(compare_township_routes(geo_session, int(plan.plan_id), "bago"))

    assert compared.alternatives_available is True
    assert len(compared.alternatives) == 3
    assert compared.alternatives[0].recommended is True
    assert compared.alternatives[0].duration_s == pytest.approx(10)
    assert [item.duration_s for item in compared.alternatives] == [10, 20, 30]
    assert all(item.routing_method == "osrm_road" for item in compared.alternatives)
    stored = list(
        geo_session.scalars(
            select(TownshipRouteOption).where(TownshipRouteOption.plan_id == int(plan.plan_id))
        )
    )
    assert len(stored) == 3


def test_osrm_failure_does_not_invent_a_second_route(
    monkeypatch: pytest.MonkeyPatch,
    geo_session: Session,
    inventory_session: Session,
) -> None:
    plan = asyncio.run(_plan(geo_session, inventory_session, monkeypatch))

    async def no_roads(_points, timeout=None, alternatives=2):
        del timeout, alternatives
        return []

    async def graph_down(*_args, **_kwargs):
        raise ValueError("graph unavailable")

    monkeypatch.setattr("app.services.route_options.osrm.driving_alternatives", no_roads)
    monkeypatch.setattr("app.services.route_options.route_delivery", graph_down)
    compared = asyncio.run(compare_township_routes(geo_session, int(plan.plan_id), "bago"))

    assert compared.alternatives_available is False
    assert len(compared.alternatives) == 1
    assert compared.alternatives[0].routing_method == "straight_line_fallback"
    assert compared.alternatives[0].distance_m is not None
    assert compared.rainfall_mm is None


def test_selected_route_is_saved(
    monkeypatch: pytest.MonkeyPatch,
    geo_session: Session,
    inventory_session: Session,
) -> None:
    plan = asyncio.run(_plan(geo_session, inventory_session, monkeypatch))

    async def roads(_points, timeout=None, alternatives=2):
        del timeout, alternatives
        return [_road(15, 96.55), _road(25, 96.75)]

    async def graph_down(*_args, **_kwargs):
        raise ValueError("graph unavailable")

    monkeypatch.setattr("app.services.route_options.osrm.driving_alternatives", roads)
    monkeypatch.setattr("app.services.route_options.route_delivery", graph_down)
    asyncio.run(compare_township_routes(geo_session, int(plan.plan_id), "bago"))
    selected = select_township_route(geo_session, int(plan.plan_id), "bago", 2)

    assert selected.alternatives[1].selected is True
    assert selected.alternatives[0].selected is False
    reloaded = allocation.get_allocation_plan(geo_session, inventory_session, int(plan.plan_id))
    options = reloaded.rows[0].route_options
    assert len(options) == 2
    assert options[1].selected is True
