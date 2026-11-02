"""Parse and summarize ToPredit relief workbooks for allocation training."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

from .census import census_json_path
from .relief_baseline import _local_name_to_name_en, _township_local_from_place

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TOPREDICT_PATH = PROJECT_ROOT / "data" / "ToPredit_Excel_Data.xlsx"
TOPREDICT_TRANSLATED_PATH = PROJECT_ROOT / "data" / "ToPredit_Excel_Data_Translated.xlsx"
EDA_OUTPUT_PATH = PROJECT_ROOT / "artifacts" / "topredict_eda_summary.json"

_LOCAL_TOWNSHIP_SUFFIX = re.compile(r"^\s*(.+?)\s*မြို့နယ်")

SKU_COLUMN_HINTS: dict[str, tuple[str, str | None]] = {
    "rice": ("foods", "rice"),
    "oil": ("foods", "oil"),
    "blanket": ("utility", "blanket"),
    "t-shirt": ("clothes", "tshirt"),
    "tshirt": ("clothes", "tshirt"),
    "canned_fish": ("foods", "canned_fish"),
    "cup": ("utility", "cup"),
    "men": ("clothes", "m_cloth"),
    "women": ("clothes", "f_cloth"),
    "fund": ("fund", None),
}


@dataclass(frozen=True)
class ReliefEventRow:
    row_index: int
    place_raw: str
    place_translated: str | None
    township_name_en: str | None
    households: float
    affected_people: float
    flood_dates_raw: str | None


def _numeric(value: object) -> float:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _township_en_from_place(place: object, local_to_en: dict[str, str]) -> str | None:
    local = _township_local_from_place(place)
    if local is None:
        text = str(place or "").strip()
        match = _LOCAL_TOWNSHIP_SUFFIX.search(text.split("၊", 1)[0])
        if match:
            local = f"{match.group(1).strip()}မြို့နယ်"
    if local is None:
        return None
    return local_to_en.get(local)


def parse_relief_events(
    source_path: Path = TOPREDICT_PATH,
    translated_path: Path = TOPREDICT_TRANSLATED_PATH,
) -> list[ReliefEventRow]:
    if not source_path.is_file():
        return []
    source = pd.read_excel(source_path, sheet_name=0, header=None)
    translated = (
        pd.read_excel(translated_path, sheet_name=0, header=None)
        if translated_path.is_file()
        else None
    )
    local_to_en = _local_name_to_name_en()
    events: list[ReliefEventRow] = []
    for index, row in source.iloc[5:].iterrows():
        serial = row.iloc[0] if len(row) > 0 else None
        if pd.isna(serial):
            continue
        try:
            int(serial)
        except (TypeError, ValueError):
            continue
        place = row.iloc[1] if len(row) > 1 else None
        if place is None or (isinstance(place, float) and pd.isna(place)):
            continue
        households = _numeric(row.iloc[7] if len(row) > 7 else None)
        affected = _numeric(row.iloc[12] if len(row) > 12 else None)
        if affected <= 0:
            affected = _numeric(row.iloc[8] if len(row) > 8 else None)
        if affected <= 0:
            affected = _numeric(row.iloc[13] if len(row) > 13 else None)
        if affected <= 0 and households <= 0:
            continue
        if affected <= 0 and households > 0:
            affected = households * 4.0
        place_en = None
        if translated is not None and index in translated.index:
            place_en = translated.iloc[index, 1] if len(translated.columns) > 1 else None
            if isinstance(place_en, float) and pd.isna(place_en):
                place_en = None
            elif place_en is not None:
                place_en = str(place_en).strip()
        events.append(
            ReliefEventRow(
                row_index=int(index),
                place_raw=str(place).strip(),
                place_translated=place_en,
                township_name_en=_township_en_from_place(place, local_to_en),
                households=households,
                affected_people=affected,
                flood_dates_raw=str(row.iloc[3]).strip()
                if len(row) > 3 and not pd.isna(row.iloc[3])
                else None,
            )
        )
    return events


def _scan_translated_headers(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    frame = pd.read_excel(path, sheet_name=0, header=None, nrows=6)
    hints: list[dict[str, Any]] = []
    for col in range(frame.shape[1]):
        values = [str(frame.iloc[row, col]).strip().lower() for row in range(frame.shape[0])]
        joined = " ".join(values)
        mapped = None
        for key, sku in SKU_COLUMN_HINTS.items():
            if key in joined:
                mapped = {"category_code": sku[0], "item_code": sku[1]}
                break
        hints.append({"column_index": col, "sample_text": joined[:120], "sku_mapping": mapped})
    return hints


def create_topredict_summary(
    output_path: Path = EDA_OUTPUT_PATH,
) -> dict[str, Any]:
    events = parse_relief_events()
    by_township: dict[str, dict[str, float]] = {}
    for event in events:
        if not event.township_name_en:
            continue
        bucket = by_township.setdefault(
            event.township_name_en,
            {"relief_rows": 0.0, "households": 0.0, "affected_people": 0.0},
        )
        bucket["relief_rows"] += 1.0
        bucket["households"] += event.households
        bucket["affected_people"] += event.affected_people

    bago_2023 = [
        asdict(event)
        for event in events
        if event.township_name_en == "Bago" and event.affected_people >= 1000
    ]

    summary: dict[str, Any] = {
        "source_path": str(TOPREDICT_PATH),
        "translated_path": str(TOPREDICT_TRANSLATED_PATH),
        "relief_event_rows": len(events),
        "townships_with_relief": len(by_township),
        "township_totals": by_township,
        "translated_header_scan": _scan_translated_headers(TOPREDICT_TRANSLATED_PATH),
        "sku_column_mapping_note": (
            "Workbook rows provide households and affected people; SKU targets for ML "
            "are derived via planning ratios unless explicit SKU columns are mapped."
        ),
        "bago_high_impact_samples": bago_2023[:5],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return summary
