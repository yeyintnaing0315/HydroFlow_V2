"""High and severe flood case catalog for the dashboard."""

from __future__ import annotations

import csv
import os
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Literal

from app.schemas.api import FloodCaseCatalogResponse, FloodCaseCounts, FloodCaseItem, FloodCaseYearCount

LevelFilter = Literal["all", "high", "severe"]
SourceFilter = Literal["all", "recorded", "model"]
ViewMode = Literal["events", "days"]


def catalog_path() -> Path:
    root = Path(__file__).resolve().parents[3]
    default = root / "data" / "processed" / "flood_cases_high_severe.csv"
    configured = Path(os.getenv("FLOOD_CASES_CATALOG_PATH", default))
    return configured


def _parse_day(value: str) -> date:
    return datetime.strptime(value[:10], "%Y-%m-%d").date()


def _parse_int(value: str | None) -> int | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        return int(round(float(text)))
    except ValueError:
        return None


def _parse_float(value: str | None) -> float | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    if number != number:
        return None
    return number


def _row_to_item(row: dict[str, str]) -> FloodCaseItem:
    peak_score = _parse_float(row.get("peak_score"))
    return FloodCaseItem(
        place=row["place"].strip(),
        township_id=row["township_id"].strip(),
        depot=row["depot"].strip(),
        source=row["source"].strip(),  # type: ignore[arg-type]
        level=row["level"].strip(),  # type: ignore[arg-type]
        start_date=_parse_day(row["start_date"]),
        end_date=_parse_day(row["end_date"]),
        peak_date=_parse_day(row["peak_date"]),
        peak_score=peak_score,
        households=_parse_int(row.get("households")),
        affected_people=_parse_int(row.get("affected_people")),
        days=max(1, int(row.get("days") or "1")),
        overlap=row.get("overlap", "").strip().lower() == "yes",
    )


@lru_cache(maxsize=4)
def _load_items_cached(path_str: str, mtime: float) -> tuple[FloodCaseItem, ...]:
    path = Path(path_str)
    if not path.is_file():
        return ()
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return tuple(_row_to_item(row) for row in rows)


def _catalog_mtime(path: Path) -> float:
    if not path.is_file():
        return -1.0
    return path.stat().st_mtime


def _collapse_events(items: list[FloodCaseItem]) -> list[FloodCaseItem]:
    if not items:
        return []
    sorted_items = sorted(
        items,
        key=lambda row: (
            row.township_id,
            row.source,
            row.level,
            row.households if row.households is not None else -1,
            row.affected_people if row.affected_people is not None else -1,
            row.start_date,
        ),
    )
    merged: list[FloodCaseItem] = []
    for item in sorted_items:
        if not merged:
            merged.append(item)
            continue
        prev = merged[-1]
        same_group = (
            prev.township_id == item.township_id
            and prev.source == item.source
            and prev.level == item.level
            and prev.households == item.households
            and prev.affected_people == item.affected_people
            and prev.depot == item.depot
        )
        if same_group and prev.end_date + timedelta(days=1) == item.start_date:
            peak_score = prev.peak_score
            if item.peak_score is not None and (peak_score is None or item.peak_score > peak_score):
                peak_score = item.peak_score
                peak_date = item.peak_date
            else:
                peak_date = prev.peak_date
            merged[-1] = FloodCaseItem(
                place=prev.place,
                township_id=prev.township_id,
                depot=prev.depot,
                source=prev.source,
                level=prev.level,
                start_date=prev.start_date,
                end_date=item.end_date,
                peak_date=peak_date,
                peak_score=peak_score,
                households=prev.households,
                affected_people=prev.affected_people,
                days=(item.end_date - prev.start_date).days + 1,
                overlap=prev.overlap or item.overlap,
            )
            continue
        merged.append(item)
    return merged


def _sort_key(item: FloodCaseItem) -> tuple[int, date, str]:
    level_rank = 0 if item.level == "severe" else 1
    return (level_rank, item.peak_date, item.place.lower())


def load_catalog(
    *,
    level: LevelFilter = "all",
    source: SourceFilter = "all",
    view: ViewMode = "events",
    township_id: str | None = None,
    year: int | None = None,
    limit: int = 200,
    offset: int = 0,
) -> FloodCaseCatalogResponse:
    path = catalog_path()
    items = list(_load_items_cached(str(path), _catalog_mtime(path)))

    if view == "events":
        items = _collapse_events(items)

    if level != "all":
        items = [row for row in items if row.level == level]
    if source != "all":
        items = [row for row in items if row.source == source]
    if township_id:
        needle = township_id.strip().lower()
        items = [row for row in items if row.township_id.lower() == needle]
    if year is not None:
        items = [row for row in items if row.peak_date.year == year]

    items.sort(key=_sort_key)

    severe = sum(1 for row in items if row.level == "severe")
    high = sum(1 for row in items if row.level == "high")
    recorded = sum(1 for row in items if row.source == "recorded")
    model = sum(1 for row in items if row.source == "model")
    overlap = sum(1 for row in items if row.overlap)

    years: dict[int, int] = {}
    for row in items:
        years[row.peak_date.year] = years.get(row.peak_date.year, 0) + 1
    by_year = [FloodCaseYearCount(year=y, count=c) for y, c in sorted(years.items())]

    page = items[offset : offset + limit]

    if not path.is_file():
        disclaimer = (
            "Catalog file is missing. Run scripts/flood_case_catalog.py to build "
            "data/processed/flood_cases_high_severe.csv from relief records and the served flood model."
        )
    else:
        disclaimer = (
            "Recorded rows use relief impact thresholds (high from score 500, severe from 2000). "
            "Model rows use the same single-day flood probability bands as the map (high from 50%, severe from 75%)."
        )

    return FloodCaseCatalogResponse(
        source_file=str(path.name),
        view=view,
        disclaimer=disclaimer,
        counts=FloodCaseCounts(
            total=len(items),
            severe=severe,
            high=high,
            recorded=recorded,
            model=model,
            overlap=overlap,
        ),
        by_year=by_year,
        events=page,
    )
