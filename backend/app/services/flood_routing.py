"""Flood-aware paths on a depot and township graph.

Edge cost is travel time. An edge that enters a township whose latest forecast
band is high or very high, or a township whose JRC 10-year depth is over 0.5 m,
is removed when it is only a transit hop and heavily penalized when it is the
delivery hop. OSRM draws road geometry only when that corridor is open. A blocked
corridor keeps this path and is labeled flood_aware_blocked.

A full Myanmar OSM extract is not downloaded. The depot and township graph is
the network when that extract is absent. Base travel times are cached in the
road-cache SQLite file.
"""

from __future__ import annotations

import asyncio
import heapq
import math
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cache.roads import insert_travel_edge, list_travel_edges
from app.models import TownshipForecast, TownshipStaticFeatures
from app.services import osrm

TRUCK_SPEED_MPS = 40_000 / 3_600
OSRM_ROUTE_TIMEOUT_SECONDS = 2.5
PENALTY = 50.0
NEAR_M = 15_000.0
JRC_BLOCK_DEPTH_M = 0.5
HIGH_RISK_BANDS = {"high", "very high", "severe"}


@dataclass(frozen=True)
class DeliveryCorridor:
    ordered_stop_ids: list[str]
    path: list[dict[str, float]]
    routing_method: str
    blocked_segments: list[dict[str, Any]]
    distance_m: float
    duration_s: float


def normalize_risk_band(band: str | None) -> str:
    text = (band or "").strip().lower().replace("_", " ").replace("-", " ")
    return " ".join(text.split())


def is_high_or_very_high(band: str | None) -> bool:
    """True for high, very high, and the app's top band severe."""
    return normalize_risk_band(band) in HIGH_RISK_BANDS


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lam = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lam / 2) ** 2
    return 2 * radius * math.asin(min(1.0, math.sqrt(a)))


def latest_forecasts(session: Session, planning_date: date) -> dict[str, TownshipForecast]:
    """Latest saved forecast per township, preferring the planning date."""
    rows = session.scalars(select(TownshipForecast).order_by(TownshipForecast.id.asc())).all()
    chosen: dict[str, TownshipForecast] = {}
    for row in rows:
        current = chosen.get(row.township_id)
        if current is None:
            chosen[row.township_id] = row
            continue
        row_match = row.target_date == planning_date
        current_match = current.target_date == planning_date
        if row_match and not current_match:
            chosen[row.township_id] = row
        elif row_match == current_match and (row.run_id, row.id) >= (current.run_id, current.id):
            chosen[row.township_id] = row
    return chosen


def forecast_context(session: Session, planning_date: date) -> tuple[set[str], dict[str, float]]:
    """Township ids to avoid, and flood probability from the latest forecast."""
    forecasts = latest_forecasts(session, planning_date)
    blocked = {township_id for township_id, row in forecasts.items() if is_high_or_very_high(row.risk_band)}
    probabilities: dict[str, float] = {}
    for township_id, row in forecasts.items():
        features = row.features if isinstance(row.features, dict) else {}
        horizon = features.get("horizon_3d")
        probabilities[township_id] = float(horizon) if horizon is not None else float(row.probability)
    for row in session.scalars(select(TownshipStaticFeatures)).all():
        depth = row.jrc_rp10_depth_m
        if depth is not None and float(depth) > JRC_BLOCK_DEPTH_M:
            blocked.add(row.township_id)
    return blocked, probabilities


def load_edge_index() -> dict[tuple[str, str], tuple[float, float]]:
    try:
        rows = list_travel_edges()
    except Exception:
        return {}
    index: dict[tuple[str, str], tuple[float, float]] = {}
    for row in rows:
        index[(str(row["from_id"]), str(row["to_id"]))] = (
            float(row["distance_m"]),
            float(row["duration_s"]),
        )
    return index


def _point(lat: float, lon: float) -> dict[str, float]:
    return {"latitude": float(lat), "longitude": float(lon)}


def _passes_near(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
    nodes: dict[str, tuple[float, float]],
    hazard_ids: set[str],
    endpoints: set[str],
) -> bool:
    steps = 8
    for index in range(1, steps):
        fraction = index / steps
        lat = lat1 + (lat2 - lat1) * fraction
        lon = lon1 + (lon2 - lon1) * fraction
        for node_id, (node_lat, node_lon) in nodes.items():
            if node_id in endpoints or node_id not in hazard_ids:
                continue
            if haversine_m(lat, lon, node_lat, node_lon) <= NEAR_M:
                return True
    return False


def _edge_travel(
    index: dict[tuple[str, str], tuple[float, float]],
    from_id: str,
    to_id: str,
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
    crosses_floodplain: bool,
) -> tuple[float, float]:
    cached = index.get((from_id, to_id)) or index.get((to_id, from_id))
    if cached is not None:
        return cached
    distance = haversine_m(lat1, lon1, lat2, lon2)
    duration = distance / TRUCK_SPEED_MPS if TRUCK_SPEED_MPS else 0.0
    try:
        insert_travel_edge(
            from_id=from_id,
            to_id=to_id,
            distance_m=distance,
            duration_s=duration,
            crosses_floodplain=crosses_floodplain,
            geometry={
                "type": "LineString",
                "coordinates": [[lon1, lat1], [lon2, lat2]],
            },
        )
    except Exception:
        pass
    index[(from_id, to_id)] = (distance, duration)
    return distance, duration


def _adjacency(
    nodes: dict[str, tuple[float, float]],
    hazard_ids: set[str],
    edge_index: dict[tuple[str, str], tuple[float, float]],
) -> dict[str, list[tuple[str, float, float, bool]]]:
    """Directed edges: to_id, duration_s, distance_m, blocked."""
    graph: dict[str, list[tuple[str, float, float, bool]]] = {node_id: [] for node_id in nodes}
    identifiers = list(nodes)
    for from_id in identifiers:
        lat1, lon1 = nodes[from_id]
        for to_id in identifiers:
            if from_id == to_id:
                continue
            lat2, lon2 = nodes[to_id]
            blocked = to_id in hazard_ids or _passes_near(
                lat1, lon1, lat2, lon2, nodes, hazard_ids, {from_id, to_id}
            )
            distance, duration = _edge_travel(
                edge_index, from_id, to_id, lat1, lon1, lat2, lon2, blocked
            )
            graph[from_id].append((to_id, duration, distance, blocked))
    return graph


def _shortest_path(
    graph: dict[str, list[tuple[str, float, float, bool]]],
    start: str,
    goal: str,
    *,
    remove_transit: bool,
) -> tuple[list[str], bool] | None:
    if start == goal:
        return [start], False
    heap: list[tuple[float, str]] = [(0.0, start)]
    best: dict[str, float] = {start: 0.0}
    previous: dict[str, str] = {}
    entered_blocked: dict[str, bool] = {start: False}
    while heap:
        cost, node = heapq.heappop(heap)
        if cost > best.get(node, math.inf):
            continue
        if node == goal:
            break
        for to_id, duration, _distance, blocked in graph.get(node, ()):
            if remove_transit and blocked and to_id != goal:
                continue
            step = duration * (PENALTY if blocked else 1.0)
            next_cost = cost + step
            if next_cost < best.get(to_id, math.inf):
                best[to_id] = next_cost
                previous[to_id] = node
                entered_blocked[to_id] = blocked
                heapq.heappush(heap, (next_cost, to_id))
    if goal not in previous:
        return None
    path = [goal]
    blocked_any = False
    while path[-1] != start:
        blocked_any = blocked_any or entered_blocked.get(path[-1], False)
        path.append(previous[path[-1]])
    path.reverse()
    return path, blocked_any


def _link(
    graph: dict[str, list[tuple[str, float, float, bool]]],
    start: str,
    goal: str,
) -> tuple[list[str], bool]:
    avoided = _shortest_path(graph, start, goal, remove_transit=True)
    if avoided is not None:
        return avoided
    penalized = _shortest_path(graph, start, goal, remove_transit=False)
    if penalized is not None:
        return penalized[0], True
    return [start, goal], True


def _hop_cost(
    graph: dict[str, list[tuple[str, float, float, bool]]],
    start: str,
    goal: str,
    nodes: dict[str, tuple[float, float]],
) -> float:
    linked = _shortest_path(graph, start, goal, remove_transit=True)
    if linked is None:
        lat1, lon1 = nodes[start]
        lat2, lon2 = nodes[goal]
        return haversine_m(lat1, lon1, lat2, lon2) / TRUCK_SPEED_MPS
    path, blocked = linked
    total = 0.0
    for left, right in zip(path, path[1:]):
        match = next((edge for edge in graph.get(left, ()) if edge[0] == right), None)
        if match is None:
            total += haversine_m(*nodes[left], *nodes[right]) / TRUCK_SPEED_MPS
            continue
        _to_id, duration, _distance, edge_blocked = match
        total += duration * (PENALTY if edge_blocked else 1.0)
    if blocked:
        total += 1.0
    return total


def _order_stops(
    graph: dict[str, list[tuple[str, float, float, bool]]],
    origin: str,
    stop_ids: list[str],
    nodes: dict[str, tuple[float, float]],
) -> list[str]:
    remaining = list(stop_ids)
    ordered: list[str] = []
    cursor = origin
    while remaining:
        best_id = min(remaining, key=lambda stop_id: _hop_cost(graph, cursor, stop_id, nodes))
        ordered.append(best_id)
        remaining.remove(best_id)
        cursor = best_id
    return ordered


def _path_metrics(
    graph: dict[str, list[tuple[str, float, float, bool]]],
    node_ids: list[str],
) -> tuple[float, float, list[dict[str, Any]], bool]:
    distance = 0.0
    duration = 0.0
    blocked_segments: list[dict[str, Any]] = []
    blocked = False
    for left, right in zip(node_ids, node_ids[1:]):
        match = next((edge for edge in graph.get(left, ()) if edge[0] == right), None)
        if match is None:
            blocked = True
            continue
        _to_id, edge_duration, edge_distance, edge_blocked = match
        distance += edge_distance
        duration += edge_duration
        if edge_blocked:
            blocked = True
            blocked_segments.append(
                {
                    "from_id": left,
                    "to_id": right,
                    "path": [],
                }
            )
    return distance, duration, blocked_segments, blocked


async def route_delivery(
    session: Session,
    *,
    origin_id: str,
    stops: list[tuple[str, float, float]],
    nodes: list[tuple[str, float, float]],
    planning_date: date,
    edge_index: dict[tuple[str, str], tuple[float, float]] | None = None,
    use_osrm: bool = True,
) -> DeliveryCorridor:
    """Shortest flood-aware path from a depot through delivery stops and back."""
    catalog = {node_id: (lat, lon) for node_id, lat, lon in nodes}
    for stop_id, lat, lon in stops:
        catalog.setdefault(stop_id, (lat, lon))
    if origin_id not in catalog:
        raise ValueError(f"Unknown route origin {origin_id}")
    if not stops:
        return DeliveryCorridor(
            ordered_stop_ids=[],
            path=[],
            routing_method="straight_line_fallback",
            blocked_segments=[],
            distance_m=0.0,
            duration_s=0.0,
        )

    hazard_ids, _probabilities = forecast_context(session, planning_date)
    index = edge_index if edge_index is not None else load_edge_index()
    graph = _adjacency(catalog, hazard_ids, index)
    ordered = _order_stops(graph, origin_id, [stop_id for stop_id, _lat, _lon in stops], catalog)

    sequence = [origin_id]
    corridor_blocked = False
    cursor = origin_id
    for stop_id in ordered:
        hop, hop_blocked = _link(graph, cursor, stop_id)
        if hop and hop[0] == cursor:
            sequence.extend(hop[1:])
        else:
            sequence.append(stop_id)
        corridor_blocked = corridor_blocked or hop_blocked
        cursor = stop_id
    return_hop, return_blocked = _link(graph, cursor, origin_id)
    if return_hop and return_hop[0] == cursor:
        sequence.extend(return_hop[1:])
    corridor_blocked = corridor_blocked or return_blocked

    distance_m, duration_s, blocked_segments, metrics_blocked = _path_metrics(graph, sequence)
    corridor_blocked = corridor_blocked or metrics_blocked
    node_path = [_point(*catalog[node_id]) for node_id in sequence]
    for segment in blocked_segments:
        segment["path"] = [_point(*catalog[segment["from_id"]]), _point(*catalog[segment["to_id"]])]

    if corridor_blocked or not use_osrm:
        return DeliveryCorridor(
            ordered_stop_ids=ordered,
            path=node_path,
            routing_method="flood_aware_blocked" if corridor_blocked else "flood_aware_graph",
            blocked_segments=blocked_segments,
            distance_m=distance_m,
            duration_s=duration_s,
        )

    waypoints = [(catalog[node_id][0], catalog[node_id][1]) for node_id in sequence]
    try:
        road = await asyncio.wait_for(
            osrm.driving_path(waypoints),
            timeout=OSRM_ROUTE_TIMEOUT_SECONDS,
        )
    except (TimeoutError, asyncio.TimeoutError):
        road = None
    if road:
        return DeliveryCorridor(
            ordered_stop_ids=ordered,
            path=road,
            routing_method="osrm_road",
            blocked_segments=[],
            distance_m=distance_m,
            duration_s=duration_s,
        )
    return DeliveryCorridor(
        ordered_stop_ids=ordered,
        path=node_path,
        routing_method="straight_line_fallback",
        blocked_segments=[],
        distance_m=distance_m,
        duration_s=duration_s,
    )
