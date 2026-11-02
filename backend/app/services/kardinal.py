"""Kardinal route optimization for a caller-supplied set of coordinates.

The long-term token stays in KARDINAL_API_KEY. This module never returns it.
Plans are deleted after the solution is read. A production agency still spends
one credit per unique stop.
"""

from __future__ import annotations

import asyncio
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from app.schemas.api import RoutePlanRequest, RoutePlanResponse, RouteWaypoint
from app.services.clients import _load_project_env, redact_secret

API_ROOT = "https://app.kardinal.ai/api/v2"
TIMEOUT_SECONDS = 30.0
POLL_SECONDS = 1.0
WAIT_SECONDS = 45.0
MAX_OPTIMIZATION = "PT45S"
FLY_KMPH = 30
TERMINAL_STATES = {"optimized", "interrupted", "stopped", "deleted"}
_DURATION = re.compile(
    r"^P(?:(?P<days>\d+)D)?(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+(?:\.\d+)?)S)?)?$"
)


class KardinalConfigError(RuntimeError):
    """Raised when the Kardinal token is missing."""


class KardinalRequestError(RuntimeError):
    """Raised when Kardinal rejects or fails a route request."""


def _key() -> str:
    _load_project_env()
    key = os.getenv("KARDINAL_API_KEY", "").strip()
    if not key:
        raise KardinalConfigError("KARDINAL_API_KEY is not set")
    return key


def _headers(key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
    }


def _position(latitude: float, longitude: float) -> dict[str, float]:
    return {"lat": round(latitude, 6), "lon": round(longitude, 6)}


def _window() -> tuple[str, str]:
    begin = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    end = begin + timedelta(hours=14)
    return (
        begin.strftime("%Y-%m-%dT%H:%M:%SZ"),
        end.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


def _duration_minutes(value: str | None) -> float | None:
    if not value:
        return None
    match = _DURATION.fullmatch(value)
    if match is None:
        return None
    parts = {name: float(group or 0) for name, group in match.groupdict().items()}
    return parts["days"] * 24 * 60 + parts["hours"] * 60 + parts["minutes"] + parts["seconds"] / 60


def build_plan(data: RoutePlanRequest) -> tuple[dict[str, Any], list[str]]:
    """Build the Kardinal plan body and the assumptions that body encodes."""
    begin, end = _window()
    if data.vehicle_profile == "fly":
        profile: dict[str, Any] = {"type": "fly", "kmph": FLY_KMPH}
        profile_note = (
            f"vehicleProfile.type is fly at {FLY_KMPH} km/h. "
            "This is straight-line travel, not the road network."
        )
    else:
        profile = {"type": data.vehicle_profile}
        profile_note = (
            f"vehicleProfile.type is {data.vehicle_profile}. "
            "No vehicle weight or height was supplied, so truck restrictions are not applied."
        )
    resource: dict[str, Any] = {
        "id": "relief-vehicle",
        "vehicleProfile": profile,
        "workingTimeWindow": {"begin": begin, "end": end},
        "departure": _position(data.origin.latitude, data.origin.longitude),
    }
    if data.return_to_origin:
        resource["arrival"] = _position(data.origin.latitude, data.origin.longitude)
        return_note = "The resource departs from the origin and returns to the same coordinates."
    else:
        return_note = "arrival was not set. The tour is not required to return to the origin."
    orders = []
    for stop in data.stops:
        body: dict[str, Any] = {
            "type": "single",
            "id": stop.id,
            "position": _position(stop.latitude, stop.longitude),
            "kind": "delivery",
        }
        if data.service_minutes > 0:
            body["operationDuration"] = f"PT{data.service_minutes}M"
        orders.append({"id": f"order-{stop.id}", "stops": [body]})
    if data.service_minutes > 0:
        service_note = f"operationDuration is PT{data.service_minutes}M at every stop."
    else:
        service_note = "operationDuration was not set."
    assumptions = [
        profile_note,
        "One resource, id relief-vehicle. Fleet size was not supplied.",
        "Stops are single delivery orders. Capacities, skills, breaks, and stop time windows were not set.",
        service_note,
        f"workingTimeWindow is {begin}/{end} UTC. No shift calendar was supplied.",
        return_note,
        f"maxOptimizationDuration is {MAX_OPTIMIZATION}.",
        "The plan is deleted after the solution is read. A production key spends one credit per unique stop.",
    ]
    payload = {
        "resources": [resource],
        "orders": orders,
        "maxOptimizationDuration": MAX_OPTIMIZATION,
    }
    return payload, assumptions


def _item(payload: dict[str, Any]) -> dict[str, Any]:
    item = payload.get("item")
    if isinstance(item, dict):
        return item
    return payload


def _state_name(payload: dict[str, Any]) -> str:
    item = _item(payload)
    for name in ("state", "value"):
        value = item.get(name)
        if isinstance(value, str) and value:
            return value
    raise ValueError("Invalid Kardinal state response")


def _error_text(response: httpx.Response) -> str:
    body = response.text[:400].replace("\n", " ")
    return redact_secret(f"Kardinal HTTP {response.status_code}: {body}")


async def _checked(response: httpx.Response) -> dict[str, Any]:
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise KardinalRequestError(_error_text(exc.response)) from exc
    try:
        payload = response.json()
    except ValueError as exc:
        raise KardinalRequestError("Kardinal returned a non-JSON response") from exc
    if not isinstance(payload, dict):
        raise KardinalRequestError("Kardinal returned an unexpected response")
    return payload


def _solution(
    data: RoutePlanRequest,
    plan_id: str,
    state: str,
    payload: dict[str, Any],
    assumptions: list[str],
) -> RoutePlanResponse:
    item = _item(payload)
    by_id = {stop.id: stop for stop in data.stops}
    tours = item.get("tours") or []
    waypoints: list[RouteWaypoint] = []
    distance = 0.0
    saw_distance = False
    durations: list[str] = []
    for tour in tours:
        if not isinstance(tour, dict):
            continue
        if tour.get("distanceInKm") is not None:
            distance += float(tour["distanceInKm"])
            saw_distance = True
        if isinstance(tour.get("workingDuration"), str):
            durations.append(tour["workingDuration"])
        for point in tour.get("wayPoints") or []:
            if not isinstance(point, dict) or point.get("type") != "stop":
                continue
            stop_id = str(point.get("stopId") or "")
            known = by_id.get(stop_id)
            if known is None:
                continue
            arrival = point.get("arrivalTime")
            parsed = datetime.fromisoformat(arrival.replace("Z", "+00:00")) if isinstance(arrival, str) else None
            waypoints.append(
                RouteWaypoint(
                    stop_id=stop_id,
                    name=known.name,
                    latitude=known.latitude,
                    longitude=known.longitude,
                    arrival_time=parsed,
                    kind=str(point.get("stopKind") or "delivery"),
                )
            )
    path = []
    if waypoints:
        path.append({"latitude": data.origin.latitude, "longitude": data.origin.longitude})
        path.extend({"latitude": point.latitude, "longitude": point.longitude} for point in waypoints)
        if data.return_to_origin:
            path.append({"latitude": data.origin.latitude, "longitude": data.origin.longitude})
    unaffected = [str(stop_id) for stop_id in item.get("unaffectedStopIds") or []]
    duration = durations[0] if len(durations) == 1 else None
    minutes = _duration_minutes(duration) if duration else None
    if len(durations) > 1:
        minutes = sum(_duration_minutes(value) or 0 for value in durations)
    agency = item.get("agencyId")
    return RoutePlanResponse(
        plan_id=plan_id,
        agency_id=str(agency) if agency else None,
        state=state,
        vehicle_profile=data.vehicle_profile,
        distance_km=distance if saw_distance else None,
        duration=duration,
        duration_minutes=minutes,
        waypoints=waypoints,
        path=path,
        unaffected_stop_ids=unaffected,
        assumptions=assumptions,
    )


async def plan_route(data: RoutePlanRequest) -> RoutePlanResponse:
    key = _key()
    payload, assumptions = build_plan(data)
    headers = _headers(key)
    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
        created = await _checked(await client.post(f"{API_ROOT}/plans", headers=headers, json=payload))
        plan_id = str(_item(created).get("id") or "")
        if not plan_id:
            raise KardinalRequestError("Kardinal did not return a plan id")
        try:
            state = "waiting"
            deadline = asyncio.get_running_loop().time() + WAIT_SECONDS
            while True:
                state_payload = await _checked(
                    await client.get(f"{API_ROOT}/plans/{plan_id}/state", headers=headers)
                )
                state = _state_name(state_payload)
                if state in TERMINAL_STATES or asyncio.get_running_loop().time() >= deadline:
                    break
                await asyncio.sleep(POLL_SECONDS)
            solution = await _checked(
                await client.get(f"{API_ROOT}/plans/{plan_id}/solution", headers=headers)
            )
            return _solution(data, plan_id, state, solution, assumptions)
        finally:
            try:
                await client.delete(f"{API_ROOT}/plans/{plan_id}", headers=headers)
            except httpx.HTTPError:
                pass
