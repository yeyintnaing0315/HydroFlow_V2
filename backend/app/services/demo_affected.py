"""Deterministic demo-scale affected counts (hundreds or 10–100) per township and date.

Allocation planning does not call this scaler. The relief and census baseline
supplies affected people for a saved plan.
"""

from __future__ import annotations

from datetime import date


def _digest(key: str) -> int:
    return sum(ord(char) for char in key)


def demo_affected_people(township_id: str, planning_date: date, raw: int) -> int:
    """Map workbook/model totals to a stable demo size for planning and UI."""
    if raw <= 0:
        return 0
    seed = _digest(f"{township_id}:{planning_date.isoformat()}")
    if seed % 10 < 3:
        return 10 + (seed % 91)
    return (1 + (seed % 9)) * 100
