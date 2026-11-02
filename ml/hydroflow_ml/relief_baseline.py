"""Relief workbook baseline (ToPredit) and census joins for allocation training."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

import pandas as pd

from .census import census_json_path

TOPREDICT_DEFAULT = Path(__file__).resolve().parents[2] / "data" / "ToPredit_Excel_Data.xlsx"
_LOCAL_TOWNSHIP_SUFFIX = re.compile(r"^\s*(.+?)\s*မြို့နယ်")

BASELINE_COLUMNS = (
    "flood_probability",
    "predicted_flood",
    "township_population",
    "township_households",
    "relief_baseline_households",
    "relief_baseline_affected",
    "depot_inventory_units",
)


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
    path = census_json_path()
    payload = json.loads(path.read_text(encoding="utf-8"))
    mapping: dict[str, str] = {}
    for district in payload.get("districts", []):
        for township in district.get("townships", []):
            local = str(township.get("name_local", "")).strip()
            english = str(township.get("name_en", "")).strip()
            if local and english:
                mapping[local] = english
    return mapping


@lru_cache(maxsize=1)
def _census_by_name_en() -> dict[str, dict[str, float]]:
    path = census_json_path()
    payload = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, dict[str, float]] = {}
    for district in payload.get("districts", []):
        for township in district.get("townships", []):
            name = str(township.get("name_en", "")).strip()
            if not name:
                continue
            out[name] = {
                "township_population": float(township["population"]["total"]),
                "township_households": float(township["households"]["total"]),
            }
    return out


@lru_cache(maxsize=1)
def relief_baseline_by_name_en(path: Path = TOPREDICT_DEFAULT) -> dict[str, dict[str, float]]:
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
        households = pd.to_numeric(row.iloc[7] if len(row) > 7 else None, errors="coerce")
        affected = pd.to_numeric(row.iloc[13] if len(row) > 13 else None, errors="coerce")
        hh = 0.0 if pd.isna(households) else float(households)
        aff = 0.0 if pd.isna(affected) else float(affected)
        if aff <= 0 and hh > 0:
            aff = hh * 4.0
        bucket = totals.setdefault(
            name_en,
            {"relief_baseline_households": 0.0, "relief_baseline_affected": 0.0},
        )
        bucket["relief_baseline_households"] += hh
        bucket["relief_baseline_affected"] += aff
    return totals


def attach_baseline_columns(frame: pd.DataFrame, flood_scored: pd.DataFrame) -> pd.DataFrame:
    """Join census, ToPredit relief totals, and flood classifier outputs onto feature rows."""
    census = _census_by_name_en()
    relief = relief_baseline_by_name_en()
    township_names = frame["township"].astype(str) if "township" in frame.columns else frame["township_id"].astype(str)
    rows = []
    for index, name in township_names.items():
        census_row = census.get(name, {"township_population": 0.0, "township_households": 0.0})
        relief_row = relief.get(name, {"relief_baseline_households": 0.0, "relief_baseline_affected": 0.0})
        flood_row = flood_scored.loc[index] if index in flood_scored.index else None
        rows.append(
            {
                "township_population": census_row["township_population"],
                "township_households": census_row["township_households"],
                "relief_baseline_households": relief_row["relief_baseline_households"],
                "relief_baseline_affected": relief_row["relief_baseline_affected"],
                "flood_probability": 0.0 if flood_row is None else float(flood_row["flood_probability"]),
                "predicted_flood": 0.0 if flood_row is None else float(int(flood_row["predicted_flood"])),
                "depot_inventory_units": 0.0,
            }
        )
    baseline = pd.DataFrame(rows, index=frame.index)
    return pd.concat([frame, baseline], axis=1)
