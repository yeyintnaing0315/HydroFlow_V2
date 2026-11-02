"""On-demand depot-to-township route alternatives.

Only roads returned by OSRM or the flood-aware graph are kept. A failed router
does not add a second invented path.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import AllocationLine, AllocationPlan, TownshipRouteOption
from app.schemas.api import Coordinates, TownshipRouteComparison, TownshipRouteOptionView
from app.services import osrm
from app.services.allocation import (
    AllocationNotFound,
    AllocationStateError,
    WAREHOUSES,
    _as_dict,
    _depot_region,
    _geometry_text,
    _iter_townships,
    _optional_float,
    _path_from_geometry,
    _planning_date_for,
    _route_nodes,
)
from app.services.flood_routing import (
    NEAR_M,
    TRUCK_SPEED_MPS,
    forecast_context,
    haversine_m,
    latest_forecasts,
    route_delivery,
)

BLOCK_M = 2_000.0
EXPOSURE_RANK = {"clear": 0, "penalized": 1, "blocked": 2, "unknown": 3}


@dataclass
class _Candidate:
    path: list[dict[str, float]]
    distance_m: float | None
    duration_s: float | None
    routing_method: str
    flood_exposure: str
    blocked_segments: list[dict[str, Any]]


def _signature(path: list[dict[str, float]]) -> tuple[tuple[float, float], ...]:
    if not path:
        return ()
    step = max(1, len(path) // 8)
    return tuple(
        (round(float(point["latitude"]), 2), round(float(point["longitude"]), 2))
        for point in path[::step][:8]
    )


def _sample(path: list[dict[str, float]]) -> list[dict[str, float]]:
    if len(path) <= 40:
        return path
    last = len(path) - 1
    return [path[int(index * last / 39)] for index in range(40)]


def _score_exposure(
    path: list[dict[str, float]],
    hazards: list[tuple[str, float, float]],
    destination_id: str,
) -> tuple[str, list[dict[str, Any]]]:
    if len(path) < 2:
        return "unknown", []
    sample = _sample(path)
    blocked: list[dict[str, Any]] = []
    penalized: list[dict[str, Any]] = []
    for hazard_id, hazard_lat, hazard_lon in hazards:
        if hazard_id == destination_id or hazard_id.startswith("depot:"):
            continue
        nearest = min(
            sample,
            key=lambda point: haversine_m(point["latitude"], point["longitude"], hazard_lat, hazard_lon),
        )
        distance = haversine_m(nearest["latitude"], nearest["longitude"], hazard_lat, hazard_lon)
        segment = {
            "from_id": hazard_id,
            "to_id": destination_id,
            "path": [nearest, {"latitude": hazard_lat, "longitude": hazard_lon}],
        }
        if distance <= BLOCK_M:
            blocked.append(segment)
        elif distance <= NEAR_M:
            penalized.append(segment)
    if blocked:
        return "blocked", blocked[:5]
    if penalized:
        return "penalized", penalized[:5]
    return "clear", []


def _sort_key(candidate: _Candidate) -> tuple[int, float, float]:
    duration = candidate.duration_s if candidate.duration_s is not None else 1e18
    distance = candidate.distance_m if candidate.distance_m is not None else 1e18
    return (EXPOSURE_RANK.get(candidate.flood_exposure, 3), duration, distance)


def _choose(candidates: list[_Candidate]) -> list[_Candidate]:
    unique: list[_Candidate] = []
    seen: set[tuple[tuple[float, float], ...]] = set()
    for candidate in candidates:
        signature = _signature(candidate.path)
        if not signature or signature in seen:
            continue
        seen.add(signature)
        unique.append(candidate)
    ranked = sorted(unique, key=_sort_key)
    chosen = ranked[:3]
    flood = next(
        (
            candidate
            for candidate in ranked
            if candidate.routing_method in {"flood_aware_graph", "flood_aware_blocked"}
            and candidate.flood_exposure in {"blocked", "penalized"}
        ),
        None,
    )
    if (
        flood is not None
        and flood not in chosen
        and chosen
        and not any(candidate.flood_exposure in {"blocked", "penalized"} for candidate in chosen)
    ):
        chosen[-1] = flood
        chosen = sorted(chosen, key=_sort_key)
    return chosen


def _straight_line(origin_lat: float, origin_lon: float, latitude: float, longitude: float) -> _Candidate:
    path = [
        {"latitude": origin_lat, "longitude": origin_lon},
        {"latitude": latitude, "longitude": longitude},
        {"latitude": origin_lat, "longitude": origin_lon},
    ]
    distance = haversine_m(origin_lat, origin_lon, latitude, longitude) * 2
    duration = distance / TRUCK_SPEED_MPS if TRUCK_SPEED_MPS else None
    return _Candidate(
        path=path,
        distance_m=distance,
        duration_s=duration,
        routing_method="straight_line_fallback",
        flood_exposure="unknown",
        blocked_segments=[],
    )


def _target(
    session: Session,
    plan_id: int,
    township_id: str,
) -> tuple[AllocationPlan, date, Literal["east", "west"], float, float]:
    plan = session.get(AllocationPlan, plan_id)
    if plan is None:
        raise AllocationNotFound(f"Allocation plan {plan_id} was not found")
    on_plan = session.scalar(
        select(AllocationLine.id).where(
            AllocationLine.plan_id == plan.id,
            AllocationLine.township_id == township_id,
        )
    )
    if on_plan is None:
        raise AllocationNotFound(f"Township {township_id} is not on allocation plan {plan_id}")
    context = _as_dict(plan.plan_context)
    planning_date = _planning_date_for(session, plan, context)
    saved_map = context.get("townships") if isinstance(context.get("townships"), dict) else {}
    saved = saved_map.get(township_id) if isinstance(saved_map.get(township_id), dict) else {}
    if saved.get("latitude") is not None and saved.get("longitude") is not None:
        latitude = float(saved["latitude"])
        longitude = float(saved["longitude"])
    else:
        located = next((item for item in _iter_townships(session, [township_id]) if item.id == township_id), None)
        if located is None:
            raise AllocationStateError(f"No coordinates are stored for {township_id}")
        latitude = located.latitude
        longitude = located.longitude
    depot_region = saved.get("depot_region")
    if depot_region not in {"east", "west"}:
        depot_region = _depot_region(latitude, longitude)
    return plan, planning_date, depot_region, latitude, longitude


def _weather(
    session: Session,
    planning_date: date,
    township_id: str,
) -> tuple[float | None, float | None, float | None, str | None]:
    forecast = latest_forecasts(session, planning_date).get(township_id)
    if forecast is None:
        return None, None, None, None
    rainfall = float(forecast.rainfall_mm) if forecast.rainfall_mm is not None else None
    discharge = float(forecast.discharge_m3_s) if forecast.discharge_m3_s is not None else None
    band = str(forecast.risk_band) if forecast.risk_band else None
    return float(forecast.probability), rainfall, discharge, band


def _view_from_row(row: TownshipRouteOption) -> TownshipRouteOptionView:
    exposure = row.flood_exposure if row.flood_exposure in EXPOSURE_RANK else "unknown"
    blocked = row.blocked_segments if isinstance(row.blocked_segments, list) else []
    return TownshipRouteOptionView(
        option_index=int(row.option_index),
        label=f"Option {int(row.option_index)}",
        path=_path_from_geometry(row.geometry),
        distance_m=row.distance_m,
        duration_s=row.duration_s,
        routing_method=row.routing_method,
        flood_exposure=exposure,  # type: ignore[arg-type]
        blocked_segments=blocked,
        rainfall_mm=row.rainfall_mm,
        discharge_m3_s=row.discharge_m3_s,
        recommended=bool(row.recommended),
        selected=bool(row.selected),
    )


def option_views_for_plan(session: Session, plan_id: int) -> dict[str, list[TownshipRouteOptionView]]:
    rows = session.scalars(
        select(TownshipRouteOption)
        .where(TownshipRouteOption.plan_id == plan_id)
        .order_by(TownshipRouteOption.township_id, TownshipRouteOption.option_index)
    ).all()
    grouped: dict[str, list[TownshipRouteOptionView]] = {}
    for row in rows:
        grouped.setdefault(row.township_id, []).append(_view_from_row(row))
    return grouped


def _comparison(
    session: Session,
    plan: AllocationPlan,
    township_id: str,
    depot_region: Literal["east", "west"],
    planning_date: date,
) -> TownshipRouteComparison:
    alternatives = option_views_for_plan(session, plan.id).get(township_id, [])
    flood, rainfall, discharge, risk_band = _weather(session, planning_date, township_id)
    context = _as_dict(plan.plan_context)
    saved_map = context.get("townships") if isinstance(context.get("townships"), dict) else {}
    saved = saved_map.get(township_id) if isinstance(saved_map.get(township_id), dict) else {}
    if flood is None and "flood_probability" in saved:
        flood = _optional_float(saved.get("flood_probability"))
    if risk_band is None and saved.get("risk_band"):
        risk_band = str(saved["risk_band"])
    if rainfall is None and "rainfall_mm" in saved:
        rainfall = _optional_float(saved.get("rainfall_mm"))
    if discharge is None and "discharge_m3_s" in saved:
        discharge = _optional_float(saved.get("discharge_m3_s"))
    return TownshipRouteComparison(
        plan_id=str(plan.id),
        township_id=township_id,
        depot_region=depot_region,
        alternatives=alternatives,
        alternatives_available=len(alternatives) >= 2,
        rainfall_mm=rainfall,
        discharge_m3_s=discharge,
        flood_probability=flood,
        risk_band=risk_band,
    )


def _store_candidates(
    session: Session,
    plan_id: int,
    township_id: str,
    chosen: list[_Candidate],
    rainfall: float | None,
    discharge: float | None,
) -> None:
    session.execute(
        delete(TownshipRouteOption).where(
            TownshipRouteOption.plan_id == plan_id,
            TownshipRouteOption.township_id == township_id,
        )
    )
    for index, candidate in enumerate(chosen, start=1):
        view = TownshipRouteOptionView(
            option_index=index,
            label=f"Option {index}",
            path=[Coordinates(latitude=point["latitude"], longitude=point["longitude"]) for point in candidate.path],
            distance_m=candidate.distance_m,
            duration_s=candidate.duration_s,
            routing_method=candidate.routing_method,
            flood_exposure=candidate.flood_exposure,  # type: ignore[arg-type]
            blocked_segments=candidate.blocked_segments,
            rainfall_mm=rainfall,
            discharge_m3_s=discharge,
            recommended=index == 1,
            selected=False,
        )
        session.add(
            TownshipRouteOption(
                plan_id=plan_id,
                township_id=township_id,
                option_index=index,
                selected=False,
                recommended=index == 1,
                routing_method=view.routing_method[:40],
                flood_exposure=view.flood_exposure[:20],
                distance_m=view.distance_m,
                duration_s=view.duration_s,
                rainfall_mm=rainfall,
                discharge_m3_s=discharge,
                blocked_segments=view.blocked_segments,
                geometry=_geometry_text(view.path),
            )
        )
    session.flush()


async def compare_township_routes(
    session: Session,
    plan_id: int,
    township_id: str,
) -> TownshipRouteComparison:
    plan, planning_date, depot_region, latitude, longitude = _target(session, plan_id, township_id)
    depot = WAREHOUSES[depot_region]
    nodes = _route_nodes(session)
    hazard_ids, _probabilities = forecast_context(session, planning_date)
    node_lookup = {node_id: (lat, lon) for node_id, lat, lon in nodes}
    hazards = [
        (hazard_id, node_lookup[hazard_id][0], node_lookup[hazard_id][1])
        for hazard_id in hazard_ids
        if hazard_id in node_lookup
    ]
    candidates: list[_Candidate] = []
    try:
        roads = await asyncio.wait_for(
            osrm.driving_alternatives(
                [(depot.latitude, depot.longitude), (latitude, longitude), (depot.latitude, depot.longitude)],
                timeout=4,
            ),
            timeout=4.5,
        )
    except (TimeoutError, asyncio.TimeoutError):
        roads = []
    for road in roads:
        path = road.get("path") if isinstance(road, dict) else None
        if not isinstance(path, list) or len(path) < 2:
            continue
        exposure, segments = _score_exposure(path, hazards, township_id)
        candidates.append(
            _Candidate(
                path=path,
                distance_m=_optional_float(road.get("distance_m")),
                duration_s=_optional_float(road.get("duration_s")),
                routing_method="osrm_road",
                flood_exposure=exposure,
                blocked_segments=segments,
            )
        )
    try:
        corridor = await route_delivery(
            session,
            origin_id=f"depot:{depot_region}",
            stops=[(township_id, latitude, longitude)],
            nodes=nodes,
            planning_date=planning_date,
            edge_index={},
            use_osrm=False,
        )
    except (ValueError, KeyError, TimeoutError, asyncio.TimeoutError):
        corridor = None
    if corridor is not None and corridor.path:
        exposure, segments = _score_exposure(corridor.path, hazards, township_id)
        if corridor.routing_method == "flood_aware_blocked":
            exposure = "blocked"
            segments = corridor.blocked_segments or segments
        candidates.append(
            _Candidate(
                path=corridor.path,
                distance_m=corridor.distance_m,
                duration_s=corridor.duration_s,
                routing_method=corridor.routing_method,
                flood_exposure=exposure,
                blocked_segments=segments,
            )
        )
    chosen = _choose(candidates)
    if not chosen:
        chosen = [_straight_line(depot.latitude, depot.longitude, latitude, longitude)]
    _flood, rainfall, discharge, _band = _weather(session, planning_date, township_id)
    _store_candidates(session, plan.id, township_id, chosen, rainfall, discharge)
    return _comparison(session, plan, township_id, depot_region, planning_date)


def select_township_route(
    session: Session,
    plan_id: int,
    township_id: str,
    option_index: int,
) -> TownshipRouteComparison:
    plan, planning_date, depot_region, _latitude, _longitude = _target(session, plan_id, township_id)
    rows = list(
        session.scalars(
            select(TownshipRouteOption).where(
                TownshipRouteOption.plan_id == plan.id,
                TownshipRouteOption.township_id == township_id,
            )
        )
    )
    if not rows:
        raise AllocationStateError("Compare routes before selecting one")
    if not any(row.option_index == option_index for row in rows):
        raise AllocationStateError(f"Route option {option_index} is not available")
    for row in rows:
        row.selected = row.option_index == option_index
    session.flush()
    return _comparison(session, plan, township_id, depot_region, planning_date)
