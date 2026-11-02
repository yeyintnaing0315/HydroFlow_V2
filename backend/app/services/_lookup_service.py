"""Archive lookup service.

Provides reference lookups for past event days and the corresponding
allocation (households / affected people) figures. Used by the simulation
overlay so a chosen past flood day returns a fixed high/severe risk level
and the matching allocation need instead of a live model estimate.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from app.data._legacy_cache import index_by_date, load_cache

# Severity bands mirror the academic risk rule used elsewhere in the service.
SEVERITY_LEVELS = ("low", "moderate", "high", "severe")

# Default fallback risk when a date is not in the reference cache.
_DEFAULT_RISK = "low"


def _normalise(day: date | str) -> str:
    if isinstance(day, date):
        return day.isoformat()
    return str(day)


def get_simulation_risk(day: date | str, township: str | None = None) -> dict[str, Any]:
    """Return the cached risk level and allocation figures for a past day.

    If the day is not a known flood day, returns a low default so the live
    model estimate remains in control. Township filtering is best-effort and
    case-insensitive against the stored location text.
    """
    target = _normalise(day)
    records = index_by_date().get(target, [])
    if not records:
        return {
            "date": target,
            "risk_level": _DEFAULT_RISK,
            "severity": _DEFAULT_RISK,
            "score": 0.0,
            "households": 0,
            "affected": 0,
            "is_flood_day": False,
            "source": "model_estimate",
        }

    # Pick the highest-severity record for the day.
    order = {"severe": 3, "high": 2, "moderate": 1, "low": 0}
    best = max(records, key=lambda r: order.get(r.get("severity", "low"), 0))

    if township:
        needle = township.lower()
        matched = [r for r in records if needle in str(r.get("location", "")).lower()]
        if matched:
            best = max(matched, key=lambda r: order.get(r.get("severity", "low"), 0))

    return {
        "date": target,
        "risk_level": best.get("severity", "low"),
        "severity": best.get("severity", "low"),
        "score": float(best.get("score", 0.0)),
        "households": int(best.get("households", 0) or 0),
        "affected": int(best.get("affected", 0) or 0),
        "location": best.get("location", ""),
        "is_flood_day": True,
        "source": "archive_reference",
    }


def get_flood_allocation_areas(day: date | str) -> list[dict[str, Any]]:
    """Return allocation-need areas for a chosen flood day.

    Each entry carries households and affected people so the allocation planner
    can size shelter kits, food rations, and water for the affected area.
    """
    target = _normalise(day)
    records = index_by_date().get(target, [])
    areas = []
    for rec in records:
        areas.append(
            {
                "date": target,
                "area": rec.get("location", ""),
                "households": int(rec.get("households", 0) or 0),
                "affected_people": int(rec.get("affected", 0) or 0),
                "severity": rec.get("severity", "low"),
                "score": float(rec.get("score", 0.0)),
            }
        )
    areas.sort(key=lambda a: a["score"], reverse=True)
    return areas


def list_flood_days() -> list[str]:
    """Return every cached flood day (ISO strings), newest first."""
    return sorted(index_by_date().keys(), reverse=True)


def is_known_flood_day(day: date | str) -> bool:
    return _normalise(day) in index_by_date()


def all_records() -> list[dict]:
    return load_cache()
