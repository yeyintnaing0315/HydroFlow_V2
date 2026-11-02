"""Read/write unified offline hydrology, static rasters, and GFM validation."""

from __future__ import annotations

import json
import sqlite3
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DB_PATH = PROJECT_ROOT / "data" / "offline" / "flood_sources.sqlite"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS source_catalog (
    name TEXT PRIMARY KEY,
    role TEXT NOT NULL,
    status TEXT NOT NULL,
    detail TEXT,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS historical_daily (
    township_id TEXT NOT NULL,
    observed_on TEXT NOT NULL,
    rainfall_mm REAL,
    discharge_m3_s REAL,
    flood_label INTEGER,
    source TEXT NOT NULL,
    PRIMARY KEY (township_id, observed_on, source)
);
CREATE TABLE IF NOT EXISTS chirps_daily (
    township_id TEXT NOT NULL,
    observed_on TEXT NOT NULL,
    rainfall_mm REAL,
    PRIMARY KEY (township_id, observed_on)
);
CREATE TABLE IF NOT EXISTS hydrology_daily (
    township_id TEXT NOT NULL,
    observed_on TEXT NOT NULL,
    rainfall_mm REAL,
    discharge_m3_s REAL,
    chirps_rainfall_mm REAL,
    soil_moisture REAL,
    runoff REAL,
    temperature_c REAL,
    relative_humidity_pct REAL,
    wind_speed_m_s REAL,
    sources_json TEXT,
    PRIMARY KEY (township_id, observed_on)
);
CREATE TABLE IF NOT EXISTS glofas_forecast_daily (
    township_id TEXT NOT NULL,
    target_date TEXT NOT NULL,
    lead_days INTEGER NOT NULL,
    rainfall_mm REAL,
    discharge_m3_s REAL,
    soil_moisture REAL,
    source TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (township_id, target_date, lead_days, source)
);
CREATE TABLE IF NOT EXISTS township_static (
    township_id TEXT PRIMARY KEY,
    hydrobasin_id TEXT,
    upstream_area_km2 REAL,
    jrc_depth_100y_max_m REAL,
    jrc_pct_inundated_100y REAL,
    hand_min_m REAL,
    hand_p10_m REAL,
    hand_pct_lt_2m REAL,
    worldcover_pct_built_floodplain REAL,
    worldcover_pct_crop_floodplain REAL,
    worldcover_pct_water REAL,
    hazard_preview_path TEXT,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS gfm_validation (
    township_id TEXT NOT NULL,
    observed_on TEXT NOT NULL,
    water_fraction REAL,
    status TEXT NOT NULL,
    detail TEXT,
    PRIMARY KEY (township_id, observed_on)
);
CREATE TABLE IF NOT EXISTS live_forecast (
    township_id TEXT NOT NULL,
    target_date TEXT NOT NULL,
    rainfall_mm REAL,
    discharge_m3_s REAL,
    source TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (township_id, target_date, source)
);
"""


def db_path() -> Path:
    return DB_PATH


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.executescript(_SCHEMA)
    connection.row_factory = sqlite3.Row
    return connection


def _compact_id(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


def _resolve_ids(township_id: str) -> list[str]:
    """Match admin slug, P-code, or romanized names stored in hydrology_daily."""
    keys = [township_id.strip(), _compact_id(township_id)]
    found: list[str] = []
    for key in keys:
        if key and key not in found:
            found.append(key)
    try:
        connection = connect()
        rows = connection.execute(
            "SELECT DISTINCT township_id FROM hydrology_daily WHERE township_id LIKE ?",
            (f"%{_compact_id(township_id)[-6:]}%",),
        ).fetchall()
        for row in rows:
            tid = str(row["township_id"])
            if tid not in found:
                found.append(tid)
    except sqlite3.Error:
        pass
    return found or [township_id]


def observations_for_range(township_id: str, start: date, end: date) -> list[dict[str, Any]]:
    if not DB_PATH.is_file():
        return []
    ids = _resolve_ids(township_id)
    placeholders = ",".join("?" for _ in ids)
    query = f"""
        SELECT * FROM hydrology_daily
        WHERE township_id IN ({placeholders})
          AND observed_on >= ? AND observed_on <= ?
        ORDER BY observed_on
    """
    params: list[Any] = [*ids, start.isoformat(), end.isoformat()]
    try:
        connection = connect()
        rows = connection.execute(query, params).fetchall()
    except sqlite3.Error:
        return []
    observations: list[dict[str, Any]] = []
    for row in rows:
        day = date.fromisoformat(str(row["observed_on"]))
        rain = row["rainfall_mm"]
        discharge = row["discharge_m3_s"]
        if rain is None or discharge is None:
            continue
        sources: dict[str, str] = {}
        if row["sources_json"]:
            try:
                sources = json.loads(str(row["sources_json"]))
            except json.JSONDecodeError:
                sources = {}
        observations.append(
            {
                "date": day,
                "rainfall_mm": float(rain),
                "river_discharge_m3s": float(discharge),
                "temperature_c": None if row["temperature_c"] is None else float(row["temperature_c"]),
                "relative_humidity_pct": None
                if row["relative_humidity_pct"] is None
                else float(row["relative_humidity_pct"]),
                "wind_speed_m_s": None if row["wind_speed_m_s"] is None else float(row["wind_speed_m_s"]),
                "chirps_rainfall_mm": None
                if row["chirps_rainfall_mm"] is None
                else float(row["chirps_rainfall_mm"]),
                "soil_moisture": None if row["soil_moisture"] is None else float(row["soil_moisture"]),
                "runoff": None if row["runoff"] is None else float(row["runoff"]),
                "rainfall_source": sources.get("rainfall", "offline hydrology database"),
                "discharge_source": sources.get("discharge", "offline hydrology database"),
                "meteorology_source": sources.get("meteorology", "offline hydrology database"),
            }
        )
    return observations


def forecast_for_range(
    township_id: str, start: date, end: date, *, as_of: date | None = None
) -> list[dict[str, Any]]:
    if not DB_PATH.is_file():
        return []
    ids = _resolve_ids(township_id)
    placeholders = ",".join("?" for _ in ids)
    query = f"""
        SELECT * FROM glofas_forecast_daily
        WHERE township_id IN ({placeholders})
          AND target_date >= ? AND target_date <= ?
        ORDER BY target_date, lead_days
    """
    params: list[Any] = [*ids, start.isoformat(), end.isoformat()]
    try:
        connection = connect()
        rows = connection.execute(query, params).fetchall()
    except sqlite3.Error:
        return []
    by_day: dict[date, dict[str, Any]] = {}
    for row in rows:
        day = date.fromisoformat(str(row["target_date"]))
        if as_of is not None and row["lead_days"] is not None:
            expected = (day - as_of).days
            if expected >= 0 and int(row["lead_days"]) != expected:
                continue
        rain = row["rainfall_mm"]
        discharge = row["discharge_m3_s"]
        if rain is None and discharge is None:
            continue
        payload = by_day.setdefault(
            day,
            {
                "date": day,
                "rainfall_source": str(row["source"]),
                "discharge_source": str(row["source"]),
                "meteorology_source": str(row["source"]),
            },
        )
        if rain is not None:
            payload["rainfall_mm"] = float(rain)
        if discharge is not None:
            payload["river_discharge_m3s"] = float(discharge)
        if row["soil_moisture"] is not None:
            payload["soil_moisture"] = float(row["soil_moisture"])
    return list(by_day.values())


@lru_cache(maxsize=256)
def static_features(township_id: str) -> dict[str, Any]:
    if not DB_PATH.is_file():
        return {}
    ids = _resolve_ids(township_id)
    placeholders = ",".join("?" for _ in ids)
    try:
        connection = connect()
        row = connection.execute(
            f"SELECT * FROM township_static WHERE township_id IN ({placeholders}) LIMIT 1",
            ids,
        ).fetchone()
    except sqlite3.Error:
        return {}
    if row is None:
        return {}
    return {
        "hydrobasin_id": row["hydrobasin_id"],
        "upstream_area_km2": row["upstream_area_km2"],
        "jrc_depth_100y_max_m": row["jrc_depth_100y_max_m"],
        "jrc_pct_inundated_100y": row["jrc_pct_inundated_100y"],
        "hand_min_m": row["hand_min_m"],
        "hand_p10_m": row["hand_p10_m"],
        "hand_pct_lt_2m": row["hand_pct_lt_2m"],
        "worldcover_pct_built_floodplain": row["worldcover_pct_built_floodplain"],
        "worldcover_pct_crop_floodplain": row["worldcover_pct_crop_floodplain"],
        "worldcover_pct_water": row["worldcover_pct_water"],
        "hazard_preview_path": row["hazard_preview_path"],
    }


def save_observed_gfm(
    township_id: str,
    day: date,
    water_fraction: float,
    detail: str | None,
) -> None:
    """Store a day only when Copernicus GFM reported observed water."""
    connection = connect()
    connection.execute(
        """
        INSERT INTO gfm_validation (township_id, observed_on, water_fraction, status, detail)
        VALUES (?, ?, ?, 'observed', ?)
        ON CONFLICT(township_id, observed_on) DO UPDATE SET
            water_fraction=excluded.water_fraction,
            status='observed',
            detail=excluded.detail
        """,
        (township_id, day.isoformat(), float(water_fraction), detail),
    )
    connection.commit()


def gfm_status(township_id: str, day: date) -> dict[str, Any] | None:
    if not DB_PATH.is_file():
        return None
    ids = _resolve_ids(township_id)
    placeholders = ",".join("?" for _ in ids)
    try:
        connection = connect()
        row = connection.execute(
            f"""
            SELECT * FROM gfm_validation
            WHERE township_id IN ({placeholders}) AND observed_on = ?
            LIMIT 1
            """,
            [*ids, day.isoformat()],
        ).fetchone()
    except sqlite3.Error:
        return None
    if row is None:
        return None
    return {
        "water_fraction": row["water_fraction"],
        "status": row["status"],
        "detail": row["detail"],
    }


def upsert_hydrology_rows(rows: list[tuple[Any, ...]]) -> int:
    if not rows:
        return 0
    connection = connect()
    connection.executemany(
        """
        INSERT INTO hydrology_daily (
            township_id, observed_on, rainfall_mm, discharge_m3_s, chirps_rainfall_mm,
            soil_moisture, runoff, temperature_c, relative_humidity_pct, wind_speed_m_s, sources_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(township_id, observed_on) DO UPDATE SET
            rainfall_mm=COALESCE(excluded.rainfall_mm, hydrology_daily.rainfall_mm),
            discharge_m3_s=COALESCE(excluded.discharge_m3_s, hydrology_daily.discharge_m3_s),
            chirps_rainfall_mm=COALESCE(excluded.chirps_rainfall_mm, hydrology_daily.chirps_rainfall_mm),
            soil_moisture=COALESCE(excluded.soil_moisture, hydrology_daily.soil_moisture),
            runoff=COALESCE(excluded.runoff, hydrology_daily.runoff),
            temperature_c=COALESCE(excluded.temperature_c, hydrology_daily.temperature_c),
            relative_humidity_pct=COALESCE(
                excluded.relative_humidity_pct, hydrology_daily.relative_humidity_pct
            ),
            wind_speed_m_s=COALESCE(excluded.wind_speed_m_s, hydrology_daily.wind_speed_m_s),
            sources_json=COALESCE(excluded.sources_json, hydrology_daily.sources_json)
        """,
        rows,
    )
    connection.commit()
    return len(rows)


def hydrology_error_message(
    *,
    window_start: date,
    window_end: date,
    operational_start: date,
) -> str:
    if window_end < operational_start:
        return (
            f"Selected dates are before the supported hindcast range "
            f"({operational_start.isoformat()} onward)."
        )
    return (
        "No complete rainfall and discharge series for this township and date. "
        "Run the 2010 hydrology backfill (hydro download + collect_offline) or pick a date "
        "within the labeled relief archive (2021+)."
    )
