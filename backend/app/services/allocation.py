"""Resource allocation planning: flood-help demand, warehouse stock, routes."""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AllocationLine,
    AllocationPlan,
    DeliveryRoute,
    PredictionRun,
    RouteStop,
    StockMovement,
    Store,
    TownshipForecast,
)
from app.schemas.api import (
    AllocationLineItem,
    AllocationPlanRequest,
    AllocationShortage,
    AllocationTotals,
    AllocationTownshipRow,
    AllocationWarehouse,
    AssistancePriorityLevel,
    Coordinates,
)
from app.services import admin_areas, help_prediction, live_features, open_admin_areas, osrm
from app.services._lookup_service import get_simulation_risk, is_known_flood_day
from app.services.allocation_baseline import affected_people_for_rank, merge_planning_baseline
from app.services.allocation_prediction import allocation_model_available, predict_sku_demand
from app.services.flood_routing import (
    forecast_context,
    is_high_or_very_high,
    latest_forecasts,
    load_edge_index,
    route_delivery,
)
from app.services.geography import GeographyUnavailableError
from app.services.inventory import (
    DEFAULT_ITEM_TYPES,
    add_region_stock,
    load_catalog,
    region_snapshot,
    store_for_region,
)
from app.services.population_split import split_affected_by_sex
from app.services.prediction_timeline import map_scores_for_date
PRIORITY_WEIGHT: dict[str, int] = {
    "none": 0,
    "low": 1,
    "moderate": 2,
    "high": 3,
    "severe": 4,
}

ROUTE_LABELS = ("Route A", "Route B", "Route C")
DEPOT_LONGITUDE_SPLIT = 96.0
DEPOT_BOUNDARY_MARGIN = 0.08
MAX_STOPS_PER_ROUTE = 8
OSRM_TIMEOUT_SECONDS = float(os.getenv("ALLOCATION_OSRM_TIMEOUT_SECONDS", "4"))
SKIP_LIVE_MAP_SCORES_ON_ARCHIVE = os.getenv("ALLOCATION_SKIP_MAP_SCORES_ON_ARCHIVE", "1") != "0"

WAREHOUSES: dict[str, AllocationWarehouse] = {
    "east": AllocationWarehouse(
        id="depot-bago",
        name="Bago depot (east)",
        region="east",
        latitude=17.335,
        longitude=96.481,
    ),
    "west": AllocationWarehouse(
        id="depot-pyay",
        name="Pyay depot (west)",
        region="west",
        latitude=18.817,
        longitude=95.217,
    ),
}


class StoreStatus(BaseModel):
    id: int
    region: Literal["east", "west"]
    name: str
    latitude: float
    longitude: float
    verified_at: datetime | None = None
    verification_note: str | None = None


class AllocationRouteView(BaseModel):
    route_id: str
    stop_count: int = Field(ge=0)
    path: list[Coordinates]
    depot_region: Literal["east", "west"] = "east"
    routing_method: str = "straight_line_fallback"
    plan: None = None
    blocked_segments: list[dict[str, Any]] = Field(default_factory=list)
    distance_m: float | None = None
    duration_s: float | None = None


class AllocationPlanView(BaseModel):
    plan_id: str
    planning_date: date
    warehouse: AllocationWarehouse
    warehouses: list[AllocationWarehouse] = Field(default_factory=list)
    totals: AllocationTotals
    rows: list[AllocationTownshipRow]
    shortages: list[AllocationShortage]
    routes: list[AllocationRouteView]
    model_version: str
    disclaimer: Literal[
        "Academic allocation illustration. Not an operational dispatch plan."
    ] = "Academic allocation illustration. Not an operational dispatch plan."
    status: Literal["draft", "confirmed"] = "draft"
    prediction_run_id: int | None = None
    unverified_stores: list[StoreStatus] = Field(default_factory=list)


class AllocationConfirmResult(BaseModel):
    plan_id: str
    status: Literal["draft", "confirmed"]
    prediction_run_id: int | None = None


class AllocationPlanHistoryItem(BaseModel):
    plan_id: str
    status: Literal["draft", "confirmed"]
    created_at: datetime
    prediction_run_id: int | None = None
    planning_date: date | None = None


class AllocationNotFound(LookupError):
    """No saved allocation plan matches the id."""


class AllocationStateError(ValueError):
    """The plan or store cannot accept this action."""


@dataclass(frozen=True)
class TownshipCatalog:
    id: str
    name_en: str
    latitude: float
    longitude: float


def _count(value: float) -> int:
    return int(max(0, round(float(value))))


def _meets_min_priority(priority: str, minimum: AssistancePriorityLevel) -> bool:
    return PRIORITY_WEIGHT.get(priority, 0) >= PRIORITY_WEIGHT[minimum]


def _line_items_from_help(scored: dict[str, Any]) -> list[AllocationLineItem]:
    people = int(scored["expected_affected_people"])
    households = int(scored["expected_households"])
    food = int(scored["food_rations_3d"])
    shelter = int(scored["shelter_kits"])
    water_l = int(scored["drinking_water_liters_3d"])

    rice_bags = _count(food / 3) if food else 0
    cans = _count(households * 0.5) if households else 0
    blankets = shelter
    cups = _count(water_l / 15) if water_l else 0
    oil = _count(water_l / 40) if water_l else 0
    tshirts = _count(people * 0.4) if people else 0
    male = _count(people * 0.3) if people else 0
    female = _count(people * 0.3) if people else 0
    fuel_mmk = _count(people * 2500) if people else 0

    specs: list[tuple[str, str | None, str, str, int]] = [
        ("foods", "rice", "Rice", "bag", rice_bags),
        ("foods", "canned_fish", "Canned fish", "can", cans),
        ("utility", "blanket", "Blanket", "piece", blankets),
        ("utility", "cup", "Cup", "piece", cups),
        ("foods", "oil", "Oil", "bottle", oil),
        ("clothes", "tshirt", "T-shirt", "piece", tshirts),
        ("clothes", "m_cloth", "Men cloth", "piece", male),
        ("clothes", "f_cloth", "Women cloth", "piece", female),
        ("fund", None, "Fund", "mmk", fuel_mmk),
    ]
    items: list[AllocationLineItem] = []
    for category_code, item_code, name, unit, qty in specs:
        if qty <= 0:
            continue
        items.append(
            AllocationLineItem(
                category_code=category_code,
                item_code=item_code,
                name=name,
                unit=unit,
                requested=float(qty),
                allocated=0.0,
            )
        )
    return items


def _stock_key(category_code: str, item_code: str | None) -> tuple[str, str | None]:
    return category_code, item_code


def _available_stock(snapshot: dict[str, object]) -> dict[tuple[str, str | None], tuple[float, str, str]]:
    stock: dict[tuple[str, str | None], tuple[float, str, str]] = {}
    for klass in snapshot.get("classes", []):
        code = str(klass["code"])
        for item in klass.get("items", []):
            key = _stock_key(code, item.get("code"))
            stock[key] = (
                float(item["quantity"]),
                str(item["name"]),
                str(item["unit"]),
            )
    return stock


def _total_stock_units(stock: dict[tuple[str, str | None], tuple[float, str, str]]) -> float:
    return sum(row[0] for row in stock.values())


def _optional_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return number


def _annotate_township_row(
    row: AllocationTownshipRow,
    scored: dict[str, Any],
    forecast: TownshipForecast | None,
) -> None:
    """Attach measured flood context. A missing source stays null, including baseline zeros."""
    row.requested_total = float(sum(item.requested for item in row.line_items))
    row.allocated_total = float(sum(item.allocated for item in row.line_items))
    rain = _optional_float(scored.get("_source_rainfall_mm"))
    discharge = _optional_float(scored.get("_source_discharge_m3_s"))
    flood = _optional_float(scored.get("_source_flood_probability"))
    band: str | None = None
    if forecast is not None:
        flood = float(forecast.probability)
        if forecast.risk_band:
            band = str(forecast.risk_band)
        if forecast.rainfall_mm is not None:
            rain = float(forecast.rainfall_mm)
        if forecast.discharge_m3_s is not None:
            discharge = float(forecast.discharge_m3_s)
    row.flood_probability = flood
    row.risk_band = band
    row.rainfall_mm = rain
    row.discharge_m3_s = discharge


def _labels_from_items(items: list[AllocationLineItem]) -> tuple[str, str]:
    names = [item.name for item in items if item.requested > 0]
    qtys = [
        f"{_count(item.allocated)} {item.unit}"
        for item in items
        if item.allocated > 0
    ]
    return ", ".join(names) or "—", ", ".join(qtys) or "—"


async def _help_for_township(
    township: TownshipCatalog,
    planning_date: date,
) -> dict[str, Any] | None:
    """Score demand; use archive / workbook path first to avoid slow live API calls."""
    scored = help_prediction.predict_help_from_flood_and_inventory(
        {},
        planning_date=planning_date,
        township_name_en=township.name_en,
        township_id=township.id,
    )
    version = str(scored.get("model_version", ""))
    workbook_hit = version.startswith("flood-help-topredict") or version.endswith("archive-fallback")
    if workbook_hit or (SKIP_LIVE_MAP_SCORES_ON_ARCHIVE and is_known_flood_day(planning_date)):
        if int(scored["expected_affected_people"]) <= 0 and not bool(scored.get("predicted_help")):
            return None
        return scored

    try:
        observations = await live_features.observations_for_timeline(
            township.id,
            township.latitude,
            township.longitude,
            planning_date - timedelta(days=2),
            planning_date,
            catalog_township_id=township.id,
        )
        rows = live_features.features_on_or_after(
            observations,
            planning_date - timedelta(days=live_features.CONTEXT_DAYS),
            township.id,
            township.latitude,
            township.longitude,
        )
    except (httpx.HTTPError, ValueError):
        return scored if int(scored["expected_affected_people"]) > 0 else None
    if not rows:
        return scored if int(scored["expected_affected_people"]) > 0 else None
    match = next((row for row in rows if row["date"] == planning_date), None)
    if match is None:
        match = max(
            rows,
            key=lambda row: float(row.get("rainfall_mm") or 0) + float(row.get("river_discharge_m3s") or 0),
        )
    try:
        scored = help_prediction.predict_help(
            {key: value for key, value in match.items() if key != "date"},
            planning_date=planning_date,
            township_name_en=township.name_en,
            township_id=township.id,
        )
    except ValueError:
        return scored if int(scored.get("expected_affected_people", 0)) > 0 else None
    return scored


def _nearest_depot(latitude: float, longitude: float) -> Literal["east", "west"]:
    east = WAREHOUSES["east"]
    west = WAREHOUSES["west"]
    east_dist = (latitude - east.latitude) ** 2 + (longitude - east.longitude) ** 2
    west_dist = (latitude - west.latitude) ** 2 + (longitude - west.longitude) ** 2
    return "east" if east_dist <= west_dist else "west"


def _depot_region(latitude: float, longitude: float) -> Literal["east", "west"]:
    if longitude >= DEPOT_LONGITUDE_SPLIT + DEPOT_BOUNDARY_MARGIN:
        return "east"
    if longitude <= DEPOT_LONGITUDE_SPLIT - DEPOT_BOUNDARY_MARGIN:
        return "west"
    return _nearest_depot(latitude, longitude)


async def _high_severe_township_ids(
    geo_session: Session,
    planning_date: date,
    extra_ids: set[str] | None = None,
) -> set[str]:
    ids = set(extra_ids or ())
    saved = latest_forecasts(geo_session, planning_date)
    if saved:
        for township_id, row in saved.items():
            if row.target_date == planning_date and is_high_or_very_high(row.risk_band):
                ids.add(township_id)
        return ids

    try:
        payload = await asyncio.wait_for(map_scores_for_date(geo_session, planning_date), timeout=8)
    except (TimeoutError, asyncio.TimeoutError, Exception):
        payload = {"scores": []}
    for score in payload.get("scores", []):
        level = score.get("probability_risk_level") or score.get("risk_level")
        if level in {"high", "severe"}:
            ids.add(str(score["township_id"]))
    return ids


def _bago_areas_payload(session: Session) -> dict:
    try:
        return admin_areas.bago_areas(session)
    except GeographyUnavailableError:
        return open_admin_areas.bundled_bago_areas()


def _iter_townships(session: Session, township_ids: list[str] | None) -> list[TownshipCatalog]:
    payload = _bago_areas_payload(session)
    catalog: list[TownshipCatalog] = []
    allowed = None if township_ids is None else set(township_ids)
    for district in payload["districts"]:
        for township in district["townships"]:
            if allowed is not None and township["id"] not in allowed:
                continue
            catalog.append(
                TownshipCatalog(
                    id=str(township["id"]),
                    name_en=str(township["name_en"]),
                    latitude=float(township["latitude"]),
                    longitude=float(township["longitude"]),
                )
            )
    return catalog


def _order_stops_nearest_neighbor(
    warehouse: AllocationWarehouse,
    rows: list[AllocationTownshipRow],
) -> list[AllocationTownshipRow]:
    if len(rows) <= 1:
        return rows
    remaining = sorted(
        rows,
        key=lambda row: (
            -PRIORITY_WEIGHT.get(str(row.priority), 0),
            -row.population,
        ),
    )
    ordered = [remaining.pop(0)]
    while remaining:
        anchor = ordered[-1]

        def _distance(row: AllocationTownshipRow) -> float:
            return (row.latitude - anchor.latitude) ** 2 + (row.longitude - anchor.longitude) ** 2

        next_index = min(range(len(remaining)), key=lambda index: _distance(remaining[index]))
        ordered.append(remaining.pop(next_index))
    return ordered


def _partition_routes(
    warehouse: AllocationWarehouse,
    rows: list[AllocationTownshipRow],
) -> list[tuple[str, list[AllocationTownshipRow]]]:
    if not rows:
        return []
    ordered = _order_stops_nearest_neighbor(warehouse, rows)
    chunks: list[list[AllocationTownshipRow]] = [
        ordered[index : index + MAX_STOPS_PER_ROUTE]
        for index in range(0, len(ordered), MAX_STOPS_PER_ROUTE)
    ]
    labeled: list[tuple[str, list[AllocationTownshipRow]]] = []
    for label, group in zip(ROUTE_LABELS, chunks[: len(ROUTE_LABELS)], strict=False):
        if group:
            labeled.append((label, group))
    if len(chunks) > len(ROUTE_LABELS):
        for index, group in enumerate(chunks[len(ROUTE_LABELS) :], start=len(ROUTE_LABELS)):
            labeled.append((f"Route {chr(65 + index)}", group))
    return labeled


def _fallback_path(
    warehouse: AllocationWarehouse,
    stops: list[AllocationTownshipRow],
) -> list[dict[str, float]]:
    path = [{"latitude": warehouse.latitude, "longitude": warehouse.longitude}]
    path.extend({"latitude": row.latitude, "longitude": row.longitude} for row in stops)
    path.append({"latitude": warehouse.latitude, "longitude": warehouse.longitude})
    return path


async def _route_for_group(
    geo_session: Session,
    warehouse: AllocationWarehouse,
    route_id: str,
    stops: list[AllocationTownshipRow],
    depot_region: Literal["east", "west"],
    planning_date: date,
    nodes: list[tuple[str, float, float]],
    edge_index: dict[tuple[str, str], tuple[float, float]],
) -> AllocationRouteView:
    if not stops:
        return AllocationRouteView(
            route_id=route_id, stop_count=0, path=[], depot_region=depot_region, plan=None
        )
    try:
        corridor = await asyncio.wait_for(
            route_delivery(
                geo_session,
                origin_id=f"depot:{depot_region}",
                stops=[(row.township_id, row.latitude, row.longitude) for row in stops],
                nodes=nodes,
                planning_date=planning_date,
                edge_index=edge_index,
            ),
            timeout=OSRM_TIMEOUT_SECONDS,
        )
    except (TimeoutError, asyncio.TimeoutError):
        corridor = None
    if corridor is None or not corridor.path:
        return AllocationRouteView(
            route_id=route_id,
            stop_count=len(stops),
            path=_fallback_path(warehouse, stops),
            depot_region=depot_region,
            routing_method="straight_line_fallback",
            plan=None,
        )
    return AllocationRouteView(
        route_id=route_id,
        stop_count=len(stops),
        path=corridor.path,
        depot_region=depot_region,
        routing_method=corridor.routing_method,
        plan=None,
        blocked_segments=corridor.blocked_segments,
        distance_m=corridor.distance_m,
        duration_s=corridor.duration_s,
    )


def _allocate_from_stock(
    candidates: list[tuple[TownshipCatalog, dict[str, Any], list[AllocationLineItem], Literal["east", "west"]]],
    stock: dict[tuple[str, str | None], tuple[float, str, str]],
    remaining: dict[tuple[str, str | None], float],
) -> tuple[list[AllocationTownshipRow], float, dict[tuple[str, str | None], float]]:
    rows: list[AllocationTownshipRow] = []
    needed_units = 0.0
    for township, scored, items, depot_region in candidates:
        people = int(scored["expected_affected_people"])
        priority = str(scored["assistance_priority"])
        row_has_shortage = False
        for item in items:
            needed_units += item.requested
            key = _stock_key(item.category_code, item.item_code)
            available = remaining.get(key, 0.0)
            take = min(item.requested, available)
            item.allocated = take
            remaining[key] = available - take
            if take < item.requested:
                row_has_shortage = True
        resources_label, quantities_label = _labels_from_items(items)
        _total, affected_male, affected_female = split_affected_by_sex(township.name_en, people)
        rows.append(
            AllocationTownshipRow(
                township_id=township.id,
                township_name=township.name_en,
                latitude=township.latitude,
                longitude=township.longitude,
                population=people,
                affected_male=affected_male,
                affected_female=affected_female,
                priority=priority,  # type: ignore[arg-type]
                resources_label=resources_label,
                quantities_label=quantities_label,
                line_items=items,
                route_id="",
                depot_region=depot_region,
                has_shortage=row_has_shortage,
            )
        )
    return rows, needed_units, remaining


def _shortages_for_depot(
    requested_totals: dict[tuple[str, str | None], float],
    stock: dict[tuple[str, str | None], tuple[float, str, str]],
    depot_region: Literal["east", "west"],
) -> list[AllocationShortage]:
    shortages: list[AllocationShortage] = []
    for key, requested in sorted(requested_totals.items()):
        available = stock.get(key, (0.0, key[0], "piece"))[0]
        unmet = max(0.0, requested - available)
        if unmet <= 0:
            continue
        name, unit = stock.get(key, (0.0, key[0], "piece"))[1], stock.get(key, (0.0, key[0], "piece"))[2]
        shortages.append(
            AllocationShortage(
                category_code=key[0],
                item_code=key[1],
                name=name,
                unit=unit,
                requested=requested,
                available=available,
                unmet=unmet,
                depot_region=depot_region,
            )
        )
    return shortages


def _unmet_need(
    items: list[AllocationLineItem],
    stock: dict[tuple[str, str | None], tuple[float, str, str]],
) -> float:
    unmet = 0.0
    for item in items:
        available = stock.get(_stock_key(item.category_code, item.item_code), (0.0, "", ""))[0]
        unmet += max(0.0, float(item.requested) - float(available))
    return unmet


def _store_status(store: Store) -> StoreStatus:
    region: Literal["east", "west"] = "east" if store.region == "east" else "west"
    return StoreStatus(
        id=int(store.id),
        region=region,
        name=store.name,
        latitude=float(store.latitude),
        longitude=float(store.longitude),
        verified_at=store.verified_at,
        verification_note=store.verification_note,
    )


def _store_readiness(
    session: Session,
    regions: tuple[Literal["east", "west"], ...] | list[str],
) -> tuple[dict[str, bool], list[StoreStatus]]:
    ready: dict[str, bool] = {}
    unverified: list[StoreStatus] = []
    for region in regions:
        store = store_for_region(session, region)
        is_ready = store.verified_at is not None
        ready[region] = is_ready
        if not is_ready:
            unverified.append(_store_status(store))
    return ready, unverified


def _prediction_run_id(session: Session, planning_date: date) -> int | None:
    forecasts = latest_forecasts(session, planning_date)
    if forecasts:
        matching = [row for row in forecasts.values() if row.target_date == planning_date]
        pool = matching or list(forecasts.values())
        chosen = max(pool, key=lambda row: (row.run_id, row.id))
        return int(chosen.run_id)
    run = session.scalar(select(PredictionRun).order_by(PredictionRun.id.desc()))
    return int(run.id) if run is not None else None


def _route_nodes(session: Session) -> list[tuple[str, float, float]]:
    nodes = [
        ("depot:east", WAREHOUSES["east"].latitude, WAREHOUSES["east"].longitude),
        ("depot:west", WAREHOUSES["west"].latitude, WAREHOUSES["west"].longitude),
    ]
    for township in _iter_townships(session, None):
        nodes.append((township.id, township.latitude, township.longitude))
    return nodes


def _lat_lon(point: Coordinates | dict[str, Any]) -> tuple[float, float]:
    if isinstance(point, dict):
        return float(point["latitude"]), float(point["longitude"])
    return float(point.latitude), float(point.longitude)


def _geometry_text(path: list[Coordinates] | list[dict[str, Any]]) -> str | None:
    if len(path) < 2:
        return None
    coordinates = [[_lat_lon(point)[1], _lat_lon(point)[0]] for point in path]
    return json.dumps({"type": "LineString", "coordinates": coordinates})


def _path_from_geometry(raw: str | None) -> list[Coordinates]:
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return []
    coords = payload.get("coordinates") if isinstance(payload, dict) else None
    if not isinstance(coords, list):
        return []
    path: list[Coordinates] = []
    for pair in coords:
        if not isinstance(pair, (list, tuple)) or len(pair) < 2:
            continue
        path.append(Coordinates(latitude=float(pair[1]), longitude=float(pair[0])))
    return path


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _plan_context_payload(
    *,
    planning_date: date,
    model_version: str,
    available_stock_units: float,
    resources_needed_units: float,
    affected_population: int,
    rows: list[AllocationTownshipRow],
    shortages: list[AllocationShortage],
) -> dict[str, Any]:
    return {
        "planning_date": planning_date.isoformat(),
        "model_version": model_version,
        "available_stock_units": available_stock_units,
        "resources_needed_units": resources_needed_units,
        "affected_population": affected_population,
        "townships": {
            row.township_id: {
                "name": row.township_name,
                "latitude": row.latitude,
                "longitude": row.longitude,
                "affected_people": row.population,
                "affected_male": row.affected_male,
                "affected_female": row.affected_female,
                "depot_region": row.depot_region,
                "route_id": row.route_id,
                "priority": row.priority,
                "flood_probability": row.flood_probability,
                "risk_band": row.risk_band,
                "rainfall_mm": row.rainfall_mm,
                "discharge_m3_s": row.discharge_m3_s,
            }
            for row in rows
        },
        "shortages": [item.model_dump() for item in shortages],
    }


def _planning_date_for(session: Session, plan: AllocationPlan, context: dict[str, Any]) -> date:
    raw = context.get("planning_date")
    if isinstance(raw, str):
        try:
            return date.fromisoformat(raw[:10])
        except ValueError:
            pass
    if plan.prediction_run_id is not None:
        run = session.get(PredictionRun, plan.prediction_run_id)
        if run is not None:
            return run.as_of
    created = plan.created_at
    return created.date()


def _priority_level(value: object) -> AssistancePriorityLevel:
    text = str(value or "")
    if text in PRIORITY_WEIGHT:
        return text  # type: ignore[return-value]
    return "none"


def _item_names(inventory_session: Session) -> dict[tuple[str, str | None], tuple[str, str]]:
    names: dict[tuple[str, str | None], tuple[str, str]] = {("fund", None): ("Fund", "mmk")}
    for category_code, types in DEFAULT_ITEM_TYPES.items():
        for code, name, unit, _order in types:
            names[(category_code, code)] = (name, unit)
    try:
        categories, types_by_category = load_catalog(inventory_session)
    except Exception:
        return names
    for category in categories:
        if category.code == "fund":
            names[(category.code, None)] = (category.name, "mmk")
        for item in types_by_category.get(category.code, []):
            names[(category.code, item.code)] = (item.name, item.unit)
    return names


def _assert_stock_covers(
    inventory_session: Session,
    needed: dict[tuple[str, str, str | None], Decimal],
) -> None:
    if not needed:
        return
    snapshots: dict[str, dict[tuple[str, str | None], tuple[float, str, str]]] = {}
    shortfalls: list[str] = []
    for region, category_code, item_code in needed:
        if region not in snapshots:
            snapshots[region] = _available_stock(region_snapshot(inventory_session, region))
        available = Decimal(str(snapshots[region].get((category_code, item_code), (0.0, "", ""))[0]))
        required = needed[(region, category_code, item_code)]
        if available < required:
            label = item_code or category_code
            shortfalls.append(f"{region} {label}: need {required}, on hand {available}")
    if shortfalls:
        raise AllocationStateError("Inventory no longer covers this plan: " + "; ".join(shortfalls))


def _save_delivery_route(
    session: Session,
    plan_id: int,
    region: Literal["east", "west"],
    label: str,
    stops: list[AllocationTownshipRow],
    view: AllocationRouteView,
) -> None:
    store = store_for_region(session, region)
    delivery = DeliveryRoute(
        plan_id=plan_id,
        store_id=store.id,
        label=label,
        routing_method=view.routing_method[:40],
        distance_m=view.distance_m,
        duration_s=view.duration_s,
        blocked_segments=view.blocked_segments,
        geometry=_geometry_text(view.path),
    )
    session.add(delivery)
    session.flush()
    for seq, stop in enumerate(stops, start=1):
        session.add(RouteStop(route_id=delivery.id, seq=seq, township_id=stop.township_id))


def list_store_status(session: Session) -> list[StoreStatus]:
    return [_store_status(store_for_region(session, region)) for region in ("east", "west")]


def verify_store(session: Session, region: str, note: str | None = None) -> StoreStatus:
    if region not in {"east", "west"}:
        raise AllocationStateError("Region must be east or west")
    store = store_for_region(session, region)
    store.verified_at = datetime.now(timezone.utc)
    store.verification_note = note
    session.flush()
    return _store_status(store)


def list_allocation_plans(session: Session) -> list[AllocationPlanHistoryItem]:
    plans = session.scalars(select(AllocationPlan).order_by(AllocationPlan.id.desc())).all()
    items: list[AllocationPlanHistoryItem] = []
    for plan in plans:
        planning_date = None
        if plan.prediction_run_id is not None:
            run = session.get(PredictionRun, plan.prediction_run_id)
            if run is not None:
                planning_date = run.as_of
        status: Literal["draft", "confirmed"] = "confirmed" if plan.status == "confirmed" else "draft"
        items.append(
            AllocationPlanHistoryItem(
                plan_id=str(plan.id),
                status=status,
                created_at=plan.created_at,
                prediction_run_id=plan.prediction_run_id,
                planning_date=planning_date,
            )
        )
    return items


def get_allocation_plan(
    geo_session: Session,
    inventory_session: Session,
    plan_id: int,
) -> AllocationPlanView:
    """Rebuild a saved plan from its lines, routes, and the snapshot stored at planning time."""
    plan = geo_session.get(AllocationPlan, plan_id)
    if plan is None:
        raise AllocationNotFound(f"Allocation plan {plan_id} was not found")
    context = _as_dict(plan.plan_context)
    planning_date = _planning_date_for(geo_session, plan, context)
    township_ctx = context.get("townships") if isinstance(context.get("townships"), dict) else {}
    names = _item_names(inventory_session)
    catalog = {item.id: item for item in _iter_townships(geo_session, None)}
    lines = list(
        geo_session.scalars(
            select(AllocationLine).where(AllocationLine.plan_id == plan.id).order_by(AllocationLine.id)
        )
    )
    grouped: dict[str, list[AllocationLine]] = {}
    for line in lines:
        grouped.setdefault(line.township_id, []).append(line)

    routes = list(geo_session.scalars(select(DeliveryRoute).where(DeliveryRoute.plan_id == plan.id)))
    route_views: list[AllocationRouteView] = []
    township_route: dict[str, str] = {}
    township_depot: dict[str, Literal["east", "west"]] = {}
    for delivery in routes:
        store = geo_session.get(Store, delivery.store_id)
        region: Literal["east", "west"] = "west" if store is not None and store.region == "west" else "east"
        stops = list(
            geo_session.scalars(
                select(RouteStop).where(RouteStop.route_id == delivery.id).order_by(RouteStop.seq)
            )
        )
        for stop in stops:
            township_route[stop.township_id] = delivery.label
            township_depot[stop.township_id] = region
        blocked = delivery.blocked_segments if isinstance(delivery.blocked_segments, list) else []
        route_views.append(
            AllocationRouteView(
                route_id=delivery.label,
                stop_count=len(stops),
                path=_path_from_geometry(delivery.geometry),
                depot_region=region,
                routing_method=delivery.routing_method or "straight_line_fallback",
                blocked_segments=blocked,
                distance_m=delivery.distance_m,
                duration_s=delivery.duration_s,
            )
        )

    from app.services.route_options import option_views_for_plan

    saved_options = option_views_for_plan(geo_session, plan.id)
    forecasts = latest_forecasts(geo_session, planning_date)
    rows: list[AllocationTownshipRow] = []
    for township_id, township_lines in grouped.items():
        saved = township_ctx.get(township_id) if isinstance(township_ctx.get(township_id), dict) else {}
        located = catalog.get(township_id)
        if saved.get("latitude") is not None and saved.get("longitude") is not None:
            latitude = float(saved["latitude"])
            longitude = float(saved["longitude"])
        elif located is not None:
            latitude = located.latitude
            longitude = located.longitude
        else:
            continue
        name = str(saved.get("name") or (located.name_en if located is not None else township_id))
        if "affected_people" in saved and saved.get("affected_people") is not None:
            population = int(saved["affected_people"])
            if saved.get("affected_male") is not None and saved.get("affected_female") is not None:
                affected_male = int(saved["affected_male"])
                affected_female = int(saved["affected_female"])
            else:
                _total, affected_male, affected_female = split_affected_by_sex(name, population)
        else:
            population = 0
            affected_male = 0
            affected_female = 0
        items: list[AllocationLineItem] = []
        for line in township_lines:
            item_name, unit = names.get(
                (line.category_code, line.item_code),
                (line.item_code or line.category_code, "unit"),
            )
            items.append(
                AllocationLineItem(
                    category_code=line.category_code,
                    item_code=line.item_code,
                    name=item_name,
                    unit=unit,
                    requested=float(line.requested),
                    allocated=float(line.allocated),
                )
            )
        resources_label, quantities_label = _labels_from_items(items)
        depot_region = saved.get("depot_region")
        if depot_region not in {"east", "west"}:
            depot_region = township_depot.get(township_id, _depot_region(latitude, longitude))
        forecast = forecasts.get(township_id)
        flood = _optional_float(saved.get("flood_probability")) if "flood_probability" in saved else None
        risk_band = str(saved["risk_band"]) if saved.get("risk_band") else None
        rainfall = _optional_float(saved.get("rainfall_mm")) if "rainfall_mm" in saved else None
        discharge = _optional_float(saved.get("discharge_m3_s")) if "discharge_m3_s" in saved else None
        if forecast is not None and "flood_probability" not in saved:
            flood = float(forecast.probability)
            risk_band = str(forecast.risk_band) if forecast.risk_band else risk_band
            if rainfall is None and forecast.rainfall_mm is not None:
                rainfall = float(forecast.rainfall_mm)
            if discharge is None and forecast.discharge_m3_s is not None:
                discharge = float(forecast.discharge_m3_s)
        rows.append(
            AllocationTownshipRow(
                township_id=township_id,
                township_name=name,
                latitude=latitude,
                longitude=longitude,
                population=max(0, population),
                affected_male=max(0, affected_male),
                affected_female=max(0, affected_female),
                priority=_priority_level(saved.get("priority") or township_lines[0].priority),
                resources_label=resources_label,
                quantities_label=quantities_label,
                line_items=items,
                route_id=str(saved.get("route_id") or township_route.get(township_id) or ""),
                depot_region=depot_region,  # type: ignore[arg-type]
                has_shortage=any(float(line.allocated) < float(line.requested) for line in township_lines),
                flood_probability=flood,
                risk_band=risk_band,
                rainfall_mm=rainfall,
                discharge_m3_s=discharge,
                requested_total=float(sum(item.requested for item in items)),
                allocated_total=float(sum(item.allocated for item in items)),
                route_options=saved_options.get(township_id, []),
            )
        )

    shortages: list[AllocationShortage] = []
    raw_shortages = context.get("shortages")
    if isinstance(raw_shortages, list):
        for item in raw_shortages:
            if isinstance(item, dict):
                shortages.append(AllocationShortage.model_validate(item))

    if "affected_population" in context and context.get("affected_population") is not None:
        affected_population = int(context["affected_population"])
    else:
        affected_population = sum(row.population for row in rows)
    if "resources_needed_units" in context and context.get("resources_needed_units") is not None:
        needed_units = float(context["resources_needed_units"])
    else:
        needed_units = float(sum(row.requested_total for row in rows))
    available_stock = (
        float(context["available_stock_units"])
        if "available_stock_units" in context and context.get("available_stock_units") is not None
        else None
    )
    regions = list(dict.fromkeys(row.depot_region for row in rows)) or ["east"]
    warehouses = [WAREHOUSES[region] for region in regions if region in WAREHOUSES]
    if not warehouses:
        warehouses = [WAREHOUSES["east"]]
    model_version = str(context.get("model_version") or "")
    if not model_version and plan.prediction_run_id is not None:
        run = geo_session.get(PredictionRun, plan.prediction_run_id)
        if run is not None:
            model_version = run.model_version
    if not model_version:
        model_version = "saved-plan"
    unverified: list[StoreStatus] = []
    try:
        inventory_stores = list(inventory_session.scalars(select(Store)))
    except Exception:
        inventory_stores = []
    for store in inventory_stores:
        if store.region in regions and store.verified_at is None:
            unverified.append(_store_status(store))
    status: Literal["draft", "confirmed"] = "confirmed" if plan.status == "confirmed" else "draft"
    return AllocationPlanView(
        plan_id=str(plan.id),
        planning_date=planning_date,
        warehouse=warehouses[0],
        warehouses=warehouses,
        totals=AllocationTotals(
            affected_population=max(0, affected_population),
            available_stock_units=available_stock,
            resources_needed_units=max(0.0, needed_units),
        ),
        rows=rows,
        shortages=shortages,
        routes=route_views,
        model_version=model_version,
        status=status,
        prediction_run_id=plan.prediction_run_id,
        unverified_stores=unverified,
    )


def confirm_allocation_plan(
    geo_session: Session,
    inventory_session: Session,
    plan_id: int,
) -> AllocationConfirmResult:
    plan = geo_session.get(AllocationPlan, plan_id)
    if plan is None:
        raise AllocationNotFound(f"Allocation plan {plan_id} was not found")
    if plan.status == "confirmed":
        raise AllocationStateError("Plan is already confirmed")
    lines = list(geo_session.scalars(select(AllocationLine).where(AllocationLine.plan_id == plan.id)))
    routes = list(geo_session.scalars(select(DeliveryRoute).where(DeliveryRoute.plan_id == plan.id)))
    township_region: dict[str, str] = {}
    for route in routes:
        store = geo_session.get(Store, route.store_id)
        if store is None:
            continue
        stops = geo_session.scalars(
            select(RouteStop).where(RouteStop.route_id == route.id).order_by(RouteStop.seq)
        )
        for stop in stops:
            township_region[stop.township_id] = store.region
    regions_needed: set[str] = set()
    for line in lines:
        if Decimal(line.allocated) <= 0:
            continue
        region = township_region.get(line.township_id)
        if region is None:
            raise AllocationStateError(f"No depot route for {line.township_id}")
        regions_needed.add(region)
    for region in sorted(regions_needed):
        store = store_for_region(inventory_session, region)
        if store.verified_at is None:
            raise AllocationStateError(f"{store.name} is not verified")
    pending: list[tuple[AllocationLine, Decimal]] = []
    needed: dict[tuple[str, str, str | None], Decimal] = {}
    for line in lines:
        quantity = Decimal(line.allocated)
        if quantity <= 0:
            continue
        already = inventory_session.scalar(
            select(StockMovement.id).where(
                StockMovement.allocation_line_id == line.id,
                StockMovement.direction == "out",
            )
        )
        if already is not None:
            continue
        pending.append((line, quantity))
        region = township_region[line.township_id]
        key = (region, line.category_code, line.item_code)
        needed[key] = needed.get(key, Decimal("0")) + quantity
    _assert_stock_covers(inventory_session, needed)
    for line, quantity in pending:
        add_region_stock(
            inventory_session,
            region=township_region[line.township_id],
            category_code=line.category_code,
            item_code=line.item_code,
            quantity=quantity,
            entry_mode="manual",
            direction="out",
            note=f"Allocation plan {plan.id} → {line.township_id}",
            allocation_line_id=line.id,
        )
    plan.status = "confirmed"
    geo_session.flush()
    inventory_session.flush()
    return AllocationConfirmResult(
        plan_id=str(plan.id),
        status="confirmed",
        prediction_run_id=plan.prediction_run_id,
    )


async def build_allocation_plan(
    geo_session: Session,
    inventory_session: Session,
    request: AllocationPlanRequest,
) -> AllocationPlanView:
    with live_features.external_budget(0):
        return await _build_allocation_plan(geo_session, inventory_session, request)


async def _build_allocation_plan(
    geo_session: Session,
    inventory_session: Session,
    request: AllocationPlanRequest,
) -> AllocationPlanView:
    auto_depots = request.warehouse_region == "auto"
    depot_regions: tuple[Literal["east", "west"], ...]
    if auto_depots:
        depot_regions = ("east", "west")
    else:
        depot_regions = (request.warehouse_region,)

    ready_regions, unverified_stores = _store_readiness(inventory_session, depot_regions)
    stock_by_region: dict[str, dict[tuple[str, str | None], tuple[float, str, str]]] = {}
    remaining_by_region: dict[str, dict[tuple[str, str | None], float]] = {}
    for region in depot_regions:
        if not ready_regions.get(region, False):
            stock_by_region[region] = {}
            remaining_by_region[region] = {}
            continue
        snapshot = region_snapshot(inventory_session, region)
        stock_by_region[region] = _available_stock(snapshot)
        remaining_by_region[region] = {key: value[0] for key, value in stock_by_region[region].items()}

    focus_ids = set(request.township_ids or [])
    plan_ids: list[str] | None = None
    if auto_depots and request.include_all_high_severe:
        risk_ids = await _high_severe_township_ids(geo_session, request.date, focus_ids)
        if latest_forecasts(geo_session, request.date):
            # Saved forecasts already name the high and very high townships.
            # An empty set must stay empty instead of scoring every township.
            plan_ids = sorted(risk_ids)
        elif risk_ids:
            plan_ids = sorted(risk_ids)
        elif focus_ids:
            plan_ids = sorted(focus_ids)
    elif focus_ids:
        plan_ids = sorted(focus_ids)

    catalog = _iter_townships(geo_session, plan_ids)

    async def _score_one(township: TownshipCatalog) -> tuple[TownshipCatalog, dict[str, Any], list[AllocationLineItem], str] | None:
        scored = await _help_for_township(township, request.date)
        if scored is None:
            return None
        priority = str(scored["assistance_priority"])
        people = int(scored["expected_affected_people"])
        if not _meets_min_priority(priority, request.min_priority):
            return None
        if people <= 0 and not bool(scored.get("predicted_help")):
            return None
        depot_hint = _depot_region(township.latitude, township.longitude)
        depot_stock = _total_stock_units(stock_by_region.get(depot_hint, {}))
        source_flood = scored.get("flood_probability") if "flood_probability" in scored else None
        source_rain = scored.get("rainfall_mm") if "rainfall_mm" in scored else None
        if "river_discharge_m3s" in scored:
            source_discharge = scored.get("river_discharge_m3s")
        elif "discharge_m3_s" in scored:
            source_discharge = scored.get("discharge_m3_s")
        else:
            source_discharge = None
        merged = merge_planning_baseline(
            scored,
            township_name_en=township.name_en,
            depot_inventory_units=depot_stock,
        )
        merged["_source_flood_probability"] = source_flood
        merged["_source_rainfall_mm"] = source_rain
        merged["_source_discharge_m3_s"] = source_discharge
        items, sku_version = predict_sku_demand(merged)
        if not items:
            return None
        return (township, merged, items, sku_version)

    scored_results = await asyncio.gather(*(_score_one(township) for township in catalog))
    scored_candidates: list[tuple[TownshipCatalog, dict[str, Any], list[AllocationLineItem], str]] = [
        row for row in scored_results if row is not None
    ]
    if scored_candidates:
        sku_model_version = scored_candidates[0][3]
    elif allocation_model_available():
        sku_model_version = "allocation-v3"
    else:
        sku_model_version = "allocation-rules-fallback"

    forecasts = latest_forecasts(geo_session, request.date)
    _hazard_ids, flood_probabilities = forecast_context(geo_session, request.date)
    ranked: list[tuple[float, float, float, TownshipCatalog, dict[str, Any], list[AllocationLineItem], Literal["east", "west"]]] = []
    for township, scored, items, _sku_version in scored_candidates:
        if auto_depots:
            depot = _depot_region(township.latitude, township.longitude)
        else:
            depot = request.warehouse_region  # type: ignore[assignment]
        flood_probability = flood_probabilities.get(township.id)
        if flood_probability is None:
            flood_probability = float(scored.get("flood_probability") or 0.0)
        affected_rank = affected_people_for_rank(scored)
        unmet = _unmet_need(items, stock_by_region.get(depot, {}))
        ranked.append((flood_probability, affected_rank, unmet, township, scored, items, depot))
    ranked.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    rank_by_township = {item[3].id: (item[0], item[1], item[2]) for item in ranked}

    by_depot: dict[str, list[tuple[TownshipCatalog, dict[str, Any], list[AllocationLineItem], Literal["east", "west"]]]] = {
        "east": [],
        "west": [],
    }
    for _flood, _affected, _unmet, township, scored, items, depot in ranked:
        by_depot[depot].append((township, scored, items, depot))

    allocated_rows: list[AllocationTownshipRow] = []
    affected = 0
    needed_units = 0.0
    shortages: list[AllocationShortage] = []

    for region in depot_regions:
        depot_candidates = by_depot[region]
        requested_totals: dict[tuple[str, str | None], float] = {}
        for _township, _scored, items, _depot in depot_candidates:
            for item in items:
                key = _stock_key(item.category_code, item.item_code)
                requested_totals[key] = requested_totals.get(key, 0.0) + item.requested

        rows, region_needed, remaining_by_region[region] = _allocate_from_stock(
            depot_candidates,
            stock_by_region[region],
            remaining_by_region[region],
        )
        scored_lookup = {township.id: scored for township, scored, _items, _depot in depot_candidates}
        for row in rows:
            _annotate_township_row(row, scored_lookup.get(row.township_id, {}), forecasts.get(row.township_id))
        for _township, scored, _items, _depot in depot_candidates:
            affected += int(scored["expected_affected_people"])
        needed_units += region_needed
        allocated_rows.extend(rows)
        shortages.extend(
            _shortages_for_depot(requested_totals, stock_by_region[region], region)
        )

    allocated_rows.sort(
        key=lambda row: rank_by_township.get(row.township_id, (0.0, float(row.population), 0.0)),
        reverse=True,
    )

    available_stock = sum(
        _total_stock_units(stock_by_region[region]) for region in depot_regions
    )
    warehouse = WAREHOUSES["east"] if auto_depots else WAREHOUSES[request.warehouse_region]
    warehouses = [WAREHOUSES[region] for region in depot_regions]

    model_version = sku_model_version
    if scored_candidates:
        help_version = str(scored_candidates[0][1].get("model_version", "flood-help-v2"))
        model_version = f"{help_version}+{sku_model_version}"

    prediction_run_id = _prediction_run_id(geo_session, request.date)
    plan = AllocationPlan(prediction_run_id=prediction_run_id, status="draft")
    geo_session.add(plan)
    geo_session.flush()
    for row in allocated_rows:
        for item in row.line_items:
            geo_session.add(
                AllocationLine(
                    plan_id=plan.id,
                    township_id=row.township_id,
                    category_code=item.category_code,
                    item_code=item.item_code,
                    requested=item.requested,
                    allocated=item.allocated,
                    priority=str(row.priority),
                )
            )
    geo_session.flush()

    edge_index = load_edge_index()
    nodes = _route_nodes(geo_session)
    routes: list[AllocationRouteView] = []
    for region in depot_regions:
        depot_warehouse = WAREHOUSES[region]
        region_rows = [row for row in allocated_rows if row.depot_region == region]
        route_groups = _partition_routes(depot_warehouse, region_rows)
        route_map = {row.township_id: label for label, group in route_groups for row in group}
        for row in region_rows:
            row.route_id = route_map.get(row.township_id, f"{region.title()} Route A")
        for label, group in route_groups:
            view = await _route_for_group(
                geo_session,
                depot_warehouse,
                label,
                group,
                region,
                request.date,
                nodes,
                edge_index,
            )
            routes.append(view)
            _save_delivery_route(geo_session, plan.id, region, label, group, view)
    if not any(route.path for route in routes):
        origin = WAREHOUSES[depot_regions[0]]
        destination = WAREHOUSES[depot_regions[-1]]
        fallback = AllocationRouteView(
            route_id="Fallback",
            stop_count=0,
            path=[
                {"latitude": origin.latitude, "longitude": origin.longitude},
                {"latitude": destination.latitude, "longitude": destination.longitude},
                {"latitude": origin.latitude, "longitude": origin.longitude},
            ],
            depot_region=depot_regions[0],
            routing_method="straight_line_fallback",
        )
        routes.append(fallback)
        _save_delivery_route(geo_session, plan.id, depot_regions[0], "Fallback", [], fallback)
    plan.plan_context = _plan_context_payload(
        planning_date=request.date,
        model_version=model_version,
        available_stock_units=available_stock,
        resources_needed_units=needed_units,
        affected_population=affected,
        rows=allocated_rows,
        shortages=shortages,
    )
    geo_session.flush()

    return AllocationPlanView(
        plan_id=str(plan.id),
        planning_date=request.date,
        warehouse=warehouse,
        warehouses=warehouses,
        totals=AllocationTotals(
            affected_population=affected,
            available_stock_units=available_stock,
            resources_needed_units=needed_units,
        ),
        rows=allocated_rows,
        shortages=shortages,
        routes=routes,
        model_version=model_version,
        status="draft",
        prediction_run_id=prediction_run_id,
        unverified_stores=unverified_stores,
    )
