"""OSRM road previews from inventory depots to townships (allocation map idle state)."""

from __future__ import annotations

import asyncio
from typing import Literal

from app.schemas.api import Coordinates
from app.services import osrm

OSRM_CONCURRENCY = 4


async def _route_leg(
    township_id: str,
    depot_region: Literal["east", "west"],
    depot_lat: float,
    depot_lon: float,
    township_lat: float,
    township_lon: float,
) -> dict:
    points = [(depot_lat, depot_lon), (township_lat, township_lon)]
    routed = await osrm.driving_route(points, timeout=8.0)
    if routed and len(routed["path"]) >= 2:
        return {
            "township_id": township_id,
            "depot_region": depot_region,
            "path": [Coordinates(**point) for point in routed["path"]],
            "distance_m": routed.get("distance_m"),
            "routing_method": "osrm_road",
        }
    return {
        "township_id": township_id,
        "depot_region": depot_region,
        "path": [],
        "distance_m": None,
        "routing_method": "straight_line_fallback",
    }


async def preview_depot_network_routes(legs: list[dict]) -> list[dict]:
    semaphore = asyncio.Semaphore(OSRM_CONCURRENCY)

    async def guarded(leg: dict) -> dict:
        async with semaphore:
            return await _route_leg(
                str(leg["township_id"]),
                leg["depot_region"],
                float(leg["depot_latitude"]),
                float(leg["depot_longitude"]),
                float(leg["township_latitude"]),
                float(leg["township_longitude"]),
            )

    return await asyncio.gather(*(guarded(leg) for leg in legs))
