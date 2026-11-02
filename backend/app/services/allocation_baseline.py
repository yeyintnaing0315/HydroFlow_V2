"""Baseline context for allocation: census, relief workbook, and depot stock."""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

from app.services import census

# Extended allocation model inputs (allocation-v2). v1 artifacts ignore unknown keys.
BASELINE_FEATURE_NAMES = (
    "flood_probability",
    "predicted_flood",
    "township_population",
    "township_households",
    "relief_baseline_households",
    "relief_baseline_affected",
    "depot_inventory_units",
)

_LOCAL_TOWNSHIP_SUFFIX = re.compile(r"^\s*(.+?)\s*မြို့နယ်")


def topredict_path() -> Path:
    default = Path(__file__).resolve().parents[3] / "data" / "ToPredit_Excel_Data.xlsx"
    return Path(os.getenv("TOPREDICT_RELIEF_PATH", default))


def _township_local_from_place(place: object) -> str | None:
    if place is None or (isinstance(place, float) and pd.isna(place)):
        return None
    text = str(place).strip().replace("\n", " ")
    if not text:
        return None
    head = text.split("၊", 1)[0].strip()
    match = _LOCAL_TOWNSHIP_SUFFIX.match(head)
    if match:
        return f"{match.group(1).strip()}မြို့နယ်"
    if head.endswith("မြို့နယ်"):
        return head
    return None


@lru_cache(maxsize=1)
def _local_name_to_name_en() -> dict[str, str]:
    try:
        payload = json.loads(
            (Path(__file__).resolve().parents[3] / "data" / "external" / "bago_census_2024.json").read_text(
                encoding="utf-8"
            )
        )
    except OSError:
        return {}
    mapping: dict[str, str] = {}
    for district in payload.get("districts", []):
        for township in district.get("townships", []):
            local = str(township.get("name_local", "")).strip()
            english = str(township.get("name_en", "")).strip()
            if local and english:
                mapping[local] = english
    return mapping


def _numeric(value: object) -> float:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


@lru_cache(maxsize=1)
def relief_baseline_by_name_en() -> dict[str, dict[str, float]]:
    """Aggregate relief rows from ToPredit_Excel_Data.xlsx by township (English name)."""
    path = topredict_path()
    if not path.is_file():
        return {}
    frame = pd.read_excel(path, sheet_name=0, header=None)
    local_to_en = _local_name_to_name_en()
    totals: dict[str, dict[str, float]] = {}
    for _, row in frame.iloc[5:].iterrows():
        local = _township_local_from_place(row.iloc[1] if len(row) > 1 else None)
        if local is None:
            continue
        name_en = local_to_en.get(local)
        if name_en is None:
            continue
        households = _numeric(row.iloc[7] if len(row) > 7 else None)
        affected = _numeric(row.iloc[12] if len(row) > 12 else None)
        if affected <= 0:
            affected = _numeric(row.iloc[8] if len(row) > 8 else None)
        if affected <= 0:
            affected = _numeric(row.iloc[13] if len(row) > 13 else None)
        if affected <= 0 and households > 0:
            affected = households * 4.0
        bucket = totals.setdefault(
            name_en,
            {"relief_baseline_households": 0.0, "relief_baseline_affected": 0.0, "relief_row_count": 0.0},
        )
        bucket["relief_baseline_households"] += households
        bucket["relief_baseline_affected"] += affected
        bucket["relief_row_count"] += 1.0
    return totals


def census_features(township_name_en: str) -> dict[str, float]:
    try:
        profile = census.township_profile(township_name_en)
    except census.CensusUnavailableError:
        return {"township_population": 0.0, "township_households": 0.0}
    if profile is None:
        return {"township_population": 0.0, "township_households": 0.0}
    _district, township = profile
    return {
        "township_population": float(township.population.total),
        "township_households": float(township.households.total),
    }


def relief_features(township_name_en: str) -> dict[str, float]:
    row = relief_baseline_by_name_en().get(township_name_en, {})
    return {
        "relief_baseline_households": float(row.get("relief_baseline_households", 0.0)),
        "relief_baseline_affected": float(row.get("relief_baseline_affected", 0.0)),
    }


# One township plan stays within a depot that holds 20,000 of each item.
# The relief rule issues one unit per person, so the headcount is capped here.
PLANNING_PEOPLE_CAP = 1000


def cap_planning_headcount(people: int, households: int) -> tuple[int, int]:
    """Keep a township plan at or under 1,000 people. Households scale with that cap."""
    safe_people = max(0, int(people))
    safe_households = max(0, int(households))
    if safe_people <= PLANNING_PEOPLE_CAP:
        return safe_people, safe_households
    ratio = PLANNING_PEOPLE_CAP / safe_people
    return PLANNING_PEOPLE_CAP, int(round(safe_households * ratio))


def affected_people_for_rank(scored: dict[str, Any]) -> float:
    """People used to rank a township.

    The planning headcount already on the score wins, so a live or injected
    affected count is not reordered by a historical relief total. Relief fills
    in only when that headcount is missing. Census population still caps it.
    """
    people = float(scored.get("expected_affected_people") or 0.0)
    if people <= 0:
        people = float(scored.get("relief_baseline_affected") or 0.0)
    census_cap = float(scored.get("township_population") or 0.0)
    if census_cap > 0:
        people = min(people, census_cap)
    return max(0.0, people)


def merge_planning_baseline(
    scored: dict[str, Any],
    *,
    township_name_en: str,
    flood_probability: float | None = None,
    predicted_flood: bool | None = None,
    depot_inventory_units: float = 0.0,
) -> dict[str, Any]:
    """Attach census, relief workbook, flood, and inventory context for SKU demand."""
    baseline = {
        **census_features(township_name_en),
        **relief_features(township_name_en),
        "flood_probability": float(scored.get("flood_probability", flood_probability or 0.0)),
        "predicted_flood": float(
            int(scored.get("predicted_flood", predicted_flood or False))
        ),
        "depot_inventory_units": float(depot_inventory_units),
    }
    if flood_probability is not None:
        baseline["flood_probability"] = float(flood_probability)
    if predicted_flood is not None:
        baseline["predicted_flood"] = float(int(predicted_flood))
    people_cap = baseline["township_population"]
    raw_people = int(scored.get("expected_affected_people") or 0)
    if people_cap > 0:
        raw_people = min(raw_people, int(people_cap))
    people, households = cap_planning_headcount(
        raw_people,
        int(scored.get("expected_households") or 0),
    )
    scored = {
        **scored,
        "expected_affected_people": people,
        "expected_households": households,
    }
    return {**scored, **baseline}
