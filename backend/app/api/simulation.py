"""Simulation overlay API.

Exposes the local reference flood archive so a chosen past flood day returns
a fixed high/severe risk level and the matching allocation need. Risk depends
on both the date AND the township (28 townships across 6 districts). These are
local simulation values only; they do not call any external model.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.services._lookup_service import (
    get_flood_allocation_areas,
    get_simulation_risk,
    is_known_flood_day,
    list_flood_days,
)

router = APIRouter(prefix="/api/simulation", tags=["simulation"])


@router.get("/flood-days")
def list_simulation_flood_days() -> dict[str, Any]:
    """List every cached past flood day (ISO strings), newest first."""
    return {"flood_days": list_flood_days(), "count": len(list_flood_days())}


@router.get("/day/{day}")
def simulation_day(
    day: str,
    township: str | None = Query(default=None, description="Township name for place-aware risk"),
) -> dict[str, Any]:
    """Return the simulated risk level for a chosen past date + township.

    Use an ISO date (YYYY-MM-DD). Known flood days for that township return
    high/severe with cached households/affected figures; unknown days or
    townships return low so the live model stays in control.
    """
    try:
        date.fromisoformat(day)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="day must be YYYY-MM-DD") from exc

    if not is_known_flood_day(day):
        return {
            "day": day,
            "township": township,
            "is_flood_day": False,
            "risk_level": "low",
            "message": "Not a recorded flood day; live model estimate applies.",
        }

    return get_simulation_risk(day, township=township)


@router.get("/allocation/{day}")
def simulation_allocation(
    day: str,
    township: str | None = Query(default=None, description="Township name to filter allocation areas"),
) -> dict[str, Any]:
    """Return allocation-need areas for a chosen flood day.

    Each area carries households and affected people so the allocation planner
    can size shelter kits, food rations, and drinking water. Local simulation
    data only.
    """
    try:
        date.fromisoformat(day)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="day must be YYYY-MM-DD") from exc
    areas = get_flood_allocation_areas(day)
    if township:
        needle = township.lower()
        areas = [a for a in areas if needle in str(a.get("area", "")).lower()]
    if not areas:
        return {
            "day": day,
            "township": township,
            "is_flood_day": False,
            "areas": [],
            "total_households": 0,
            "total_affected": 0,
            "message": "No allocation need recorded for this day and township.",
        }
    total_households = sum(a["households"] for a in areas)
    total_affected = sum(a["affected_people"] for a in areas)
    return {
        "day": day,
        "township": township,
        "is_flood_day": True,
        "areas": areas,
        "total_households": total_households,
        "total_affected": total_affected,
        "count": len(areas),
    }
