"""Relief impacts from ToPredit workbooks (recorded flood responses)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from functools import lru_cache

import pandas as pd

from app.services.allocation_baseline import (
    _local_name_to_name_en,
    _township_local_from_place,
    topredict_path,
)

_MM_DIGIT = str.maketrans("၀၁၂၃၄၅၆၇၈၉", "0123456789")
_DATE_TOKEN = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})")


@dataclass(frozen=True)
class TopredictImpactRow:
    township_name_en: str | None
    households: int
    affected_total: int
    affected_group_a: int
    affected_group_b: int
    flood_dates_raw: str | None


def _numeric(value: object) -> float:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return 0.0
    if isinstance(value, str):
        text = value.translate(_MM_DIGIT).strip()
        if not text:
            return 0.0
        try:
            return float(text)
        except ValueError:
            return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _affected_from_row(row: pd.Series) -> tuple[float, float, float, float]:
    """Return households, total affected, group_a, group_b from workbook columns."""
    households = _numeric(row.iloc[7] if len(row) > 7 else None)
    group_a = _numeric(row.iloc[8] if len(row) > 8 else None)
    group_b = _numeric(row.iloc[9] if len(row) > 9 else None)
    total = _numeric(row.iloc[12] if len(row) > 12 else None)
    if total <= 0:
        total = _numeric(row.iloc[13] if len(row) > 13 else None)
    if total <= 0 and group_a > 0:
        total = group_a + group_b if group_b > 0 else group_a
    if total <= 0 and households > 0:
        total = households * 4.0
    return households, total, group_a, group_b


def _parse_dates(raw: object) -> list[date]:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return []
    text = str(raw).translate(_MM_DIGIT)
    found: list[date] = []
    for day, month, year in _DATE_TOKEN.findall(text):
        try:
            found.append(date(int(year), int(month), int(day)))
        except ValueError:
            continue
    return found


def _dates_cover(planning: date, raw: object) -> bool:
    tokens = _parse_dates(raw)
    if not tokens:
        return False
    if planning in tokens:
        return True
    return any(item.year == planning.year and item.month == planning.month for item in tokens)


@lru_cache(maxsize=1)
def _load_rows() -> tuple[TopredictImpactRow, ...]:
    path = topredict_path()
    if not path.is_file():
        return ()
    frame = pd.read_excel(path, sheet_name=0, header=None)
    local_to_en = _local_name_to_name_en()
    rows: list[TopredictImpactRow] = []
    for _, row in frame.iloc[5:].iterrows():
        serial = row.iloc[0] if len(row) > 0 else None
        if pd.isna(serial):
            continue
        try:
            int(serial)
        except (TypeError, ValueError):
            continue
        local = _township_local_from_place(row.iloc[1] if len(row) > 1 else None)
        if local is None:
            continue
        name_en = local_to_en.get(local)
        households, total, group_a, group_b = _affected_from_row(row)
        if total <= 0 and households <= 0:
            continue
        rows.append(
            TopredictImpactRow(
                township_name_en=name_en,
                households=int(max(0, round(households))),
                affected_total=int(max(0, round(total))),
                affected_group_a=int(max(0, round(group_a))),
                affected_group_b=int(max(0, round(group_b))),
                flood_dates_raw=str(row.iloc[3]).strip()
                if len(row) > 3 and not pd.isna(row.iloc[3])
                else None,
            )
        )
    return tuple(rows)


def impact_for_township_date(township_name_en: str, planning: date) -> dict[str, int | str] | None:
    if not township_name_en:
        return None
    needle = township_name_en.strip().lower()
    dated = [
        row
        for row in _load_rows()
        if row.township_name_en and row.township_name_en.lower() == needle and _dates_cover(planning, row.flood_dates_raw)
    ]
    matched = dated
    if not matched:
        return None

    households = sum(row.households for row in matched)
    total = sum(row.affected_total for row in matched)
    group_a = sum(row.affected_group_a for row in matched)
    group_b = sum(row.affected_group_b for row in matched)
    if total <= 0:
        return None

    payload: dict[str, int | str] = {
        "expected_affected_people": total,
        "expected_households": households,
        "source": "ToPredit_Excel_Data.xlsx",
    }
    if group_a > 0 and group_b > 0 and group_a + group_b == total:
        payload["affected_group_a"] = group_a
        payload["affected_group_b"] = group_b
    return payload
