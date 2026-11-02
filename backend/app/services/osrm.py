"""Driving paths from the public OSRM router (OpenStreetMap road network)."""

from __future__ import annotations

from typing import Any

import httpx

OSRM_ROOT = "https://router.project-osrm.org"
TIMEOUT_SECONDS = 25.0


def _parse_osrm_route(payload: object) -> dict[str, Any] | None:
    if not isinstance(payload, dict) or payload.get("code") != "Ok":
        return None
    routes = payload.get("routes")
    if not isinstance(routes, list) or not routes:
        return None
    route = routes[0]
    if not isinstance(route, dict):
        return None
    path = _line_path(route.get("geometry"))
    if not path:
        return None
    distance = route.get("distance")
    duration = route.get("duration")
    return {
        "path": path,
        "distance_m": float(distance) if isinstance(distance, (int, float)) else None,
        "duration_s": float(duration) if isinstance(duration, (int, float)) else None,
    }


async def driving_route(
    points: list[tuple[float, float]],
    *,
    timeout: float | None = None,
) -> dict[str, Any] | None:
    """Road path plus distance/duration from OSRM, or None if routing fails."""
    if len(points) < 2:
        return None
    coordinate_path = ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in points)
    url = (
        f"{OSRM_ROOT}/route/v1/driving/{coordinate_path}"
        "?overview=full&geometries=geojson&steps=false"
    )
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS if timeout is None else timeout) as client:
            response = await client.get(url)
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return None
    return _parse_osrm_route(payload)


async def driving_path(
    points: list[tuple[float, float]],
    *,
    timeout: float | None = None,
) -> list[dict[str, float]] | None:
    """Return lat/lon points along the road from OSRM, or None if routing fails."""
    routed = await driving_route(points, timeout=timeout)
    if routed is None:
        return None
    return routed["path"]


def _line_path(geometry: object) -> list[dict[str, float]] | None:
    if not isinstance(geometry, dict) or geometry.get("type") != "LineString":
        return None
    coords = geometry.get("coordinates")
    if not isinstance(coords, list):
        return None
    path: list[dict[str, float]] = []
    for pair in coords:
        if not isinstance(pair, (list, tuple)) or len(pair) < 2:
            continue
        lon, lat = float(pair[0]), float(pair[1])
        path.append({"latitude": lat, "longitude": lon})
    return path or None


async def driving_alternatives(
    points: list[tuple[float, float]],
    *,
    timeout: float | None = None,
    alternatives: int = 2,
) -> list[dict[str, Any]]:
    """Up to three real OSRM roads (primary plus alternatives). Empty when routing fails."""
    if len(points) < 2:
        return []
    coordinate_path = ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in points)
    limit = max(0, min(int(alternatives), 2))
    url = (
        f"{OSRM_ROOT}/route/v1/driving/{coordinate_path}"
        f"?overview=full&geometries=geojson&steps=false&alternatives={limit}"
    )
    try:
        async with httpx.AsyncClient(timeout=4.0 if timeout is None else timeout) as client:
            response = await client.get(url)
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return []
    if payload.get("code") != "Ok":
        return []
    routes = payload.get("routes")
    if not isinstance(routes, list):
        return []
    parsed: list[dict[str, Any]] = []
    for route in routes:
        if not isinstance(route, dict):
            continue
        path = _line_path(route.get("geometry"))
        if not path:
            continue
        distance = route.get("distance")
        duration = route.get("duration")
        parsed.append(
            {
                "path": path,
                "distance_m": float(distance) if isinstance(distance, (int, float)) else None,
                "duration_s": float(duration) if isinstance(duration, (int, float)) else None,
            }
        )
        if len(parsed) >= 3:
            break
    return parsed
