import math
import os
from datetime import date
from functools import lru_cache
from pathlib import Path

import pandas as pd

from app.schemas.api import FloodHistoryRecord


def history_path() -> Path:
    root = Path(__file__).resolve().parents[3]
    default = root / "data" / "processed" / "validated_daily.csv"
    configured = Path(os.getenv("FLOOD_HISTORY_PATH", default))
    if configured.is_file():
        return configured
    fallback = root / "data" / "raw" / "bago_daily.csv"
    if fallback.is_file():
        return fallback
    return configured


def impact_severity(households: float, affected_people: float) -> str:
    """Same retrospective thresholds as the ML severity rule."""
    score = max(0.0, households) + max(0.0, affected_people) / 5.0
    if score >= 2000:
        return "severe"
    if score >= 500:
        return "high"
    if score >= 100:
        return "moderate"
    if score > 0:
        return "low"
    return "none"


def _optional_count(value: object) -> int | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    return int(value)


@lru_cache(maxsize=1)
def _flood_days() -> pd.DataFrame:
    path = history_path()
    if not path.is_file():
        raise FileNotFoundError(path)
    frame = pd.read_csv(
        path,
        usecols=[
            "date",
            "township_id",
            "township",
            "lat",
            "lng",
            "households",
            "affected_people",
            "flood",
        ],
        parse_dates=["date"],
    )
    floods = frame.loc[frame["flood"] == 1].copy()
    return floods.sort_values(["date", "township_id"], ascending=[False, True])


@lru_cache(maxsize=1)
def list_townships() -> tuple[tuple[str, str, float, float], ...]:
    path = history_path()
    if not path.is_file():
        raise FileNotFoundError(path)
    frame = pd.read_csv(path, usecols=["township_id", "township", "lat", "lng"])
    unique = frame.drop_duplicates("township_id").sort_values("township")
    return tuple(
        (row.township_id, row.township, float(row.lat), float(row.lng))
        for row in unique.itertuples(index=False)
    )


def assistance_brief(limit: int = 5) -> dict[str, object]:
    """Aggregate recorded flood impacts for the humanitarian assistance view."""
    frame = _flood_days().copy()
    households = pd.to_numeric(frame["households"], errors="coerce").fillna(0).clip(lower=0)
    people = pd.to_numeric(frame["affected_people"], errors="coerce").fillna(0).clip(lower=0)
    frame = frame.assign(_households=households, _people=people, _score=households + people / 5.0)
    ranked = frame.sort_values(["_score", "date"], ascending=[False, False])
    records = [
        FloodHistoryRecord(
            date=pd.Timestamp(item["date"]).date(),
            township_id=str(item["township_id"]),
            township=str(item["township"]),
            latitude=float(item["lat"]),
            longitude=float(item["lng"]),
            households=_optional_count(item["households"]),
            affected_people=_optional_count(item["affected_people"]),
            impact_severity=impact_severity(float(item["_households"]), float(item["_people"])),
        )
        for item in ranked.head(limit).to_dict(orient="records")
    ]
    return {
        "recorded_flood_days": int(len(frame)),
        "recorded_households": int(round(float(households.sum()))),
        "recorded_affected_people": int(round(float(people.sum()))),
        "townships_with_impact": int(frame.loc[frame["_score"] > 0, "township_id"].nunique()),
        "highest_impacts": records,
    }


def recorded_floods(
    township_id: str | None = None,
    start: date | None = None,
    end: date | None = None,
    limit: int = 20,
) -> tuple[int, list[FloodHistoryRecord]]:
    frame = _flood_days()
    if township_id:
        frame = frame.loc[frame["township_id"] == township_id]
    if start:
        frame = frame.loc[frame["date"] >= pd.Timestamp(start)]
    if end:
        frame = frame.loc[frame["date"] <= pd.Timestamp(end)]
    matched = len(frame)
    records = [
        FloodHistoryRecord(
            date=row.date.date(),
            township_id=row.township_id,
            township=row.township,
            latitude=float(row.lat),
            longitude=float(row.lng),
            households=_optional_count(row.households),
            affected_people=_optional_count(row.affected_people),
            impact_severity=impact_severity(
                0 if pd.isna(row.households) else float(row.households),
                0 if pd.isna(row.affected_people) else float(row.affected_people),
            ),
        )
        for row in frame.head(limit).itertuples(index=False)
    ]
    return matched, records
