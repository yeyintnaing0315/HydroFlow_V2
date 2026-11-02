"""Offline flood database: hydrology 2010+, CHIRPS, CEMS GloFAS, live forecast, static rasters."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.hydro_history import APP_HISTORY_START  # noqa: E402
from app.services.hydro_sources import HYDRO_MERGED_DIR  # noqa: E402

DB_PATH = ROOT / "data" / "offline" / "flood_sources.sqlite"
DAILY_PATH = ROOT / "data" / "processed" / "validated_daily.csv"
RIVER_POINTS = ROOT / "data" / "external" / "bago_river_points.csv"
CHIRPS_RANGE_START = APP_HISTORY_START


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.executescript(
        """
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
    )
    return connection


def _catalog(connection: sqlite3.Connection, name: str, role: str, status: str, detail: str) -> None:
    connection.execute(
        """
        INSERT INTO source_catalog (name, role, status, detail, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(name) DO UPDATE SET
            role=excluded.role, status=excluded.status, detail=excluded.detail, updated_at=excluded.updated_at
        """,
        (name, role, status, detail, date.today().isoformat()),
    )


def _slug(name: str) -> str:
    return "".join(character if character.isalnum() else "_" for character in name.casefold()).strip("_")


def _store_history(connection: sqlite3.Connection) -> int:
    if not DAILY_PATH.is_file():
        return 0
    frame = pd.read_csv(DAILY_PATH, usecols=["date", "township_id", "rainfall_mm", "river_discharge_m3s", "flood"])
    rows = [
        (
            str(row.township_id),
            str(row.date)[:10],
            None if pd.isna(row.rainfall_mm) else float(row.rainfall_mm),
            None if pd.isna(row.river_discharge_m3s) else float(row.river_discharge_m3s),
            None if pd.isna(row.flood) else int(row.flood),
            "validated_daily",
        )
        for row in frame.itertuples(index=False)
    ]
    connection.executemany(
        """
        INSERT INTO historical_daily (township_id, observed_on, rainfall_mm, discharge_m3_s, flood_label, source)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(township_id, observed_on, source) DO UPDATE SET
            rainfall_mm=excluded.rainfall_mm,
            discharge_m3_s=excluded.discharge_m3_s,
            flood_label=excluded.flood_label
        """,
        rows,
    )
    return len(rows)


def _store_hydrology_from_merged(connection: sqlite3.Connection) -> int:
    if not HYDRO_MERGED_DIR.is_dir():
        return 0
    paths = sorted(HYDRO_MERGED_DIR.glob("*.csv"), key=lambda item: (0 if item.stem.upper().startswith("MMR") else 1, item.name))
    seen_stems: set[str] = set()
    saved = 0
    for path in paths:
        if path.stem in seen_stems:
            continue
        try:
            frame = pd.read_csv(path, parse_dates=["date"])
        except (OSError, ValueError):
            continue
        if len(frame) < 30:
            continue
        seen_stems.add(path.stem)
        township_id = path.stem
        if "township_id" in frame.columns and frame["township_id"].notna().any():
            township_id = str(frame["township_id"].dropna().iloc[0])
        batch: list[tuple] = []
        for record in frame.itertuples(index=False):
            day = str(record.date)[:10]
            rain = getattr(record, "rainfall_mm", None)
            if rain is None or pd.isna(rain):
                rain = getattr(record, "precipitation_mm", None)
            discharge = getattr(record, "river_discharge_m3s", None)
            if rain is None or pd.isna(rain) or discharge is None or pd.isna(discharge):
                continue
            sources = json.dumps(
                {
                    "rainfall": "local open_meteo_archive_daily",
                    "discharge": "local glofas_discharge",
                    "meteorology": "local nasa_power_hydro",
                }
            )
            batch.append(
                (
                    township_id,
                    day,
                    float(rain),
                    float(discharge),
                    None,
                    None,
                    None,
                    None if not hasattr(record, "temperature_c") or pd.isna(record.temperature_c) else float(record.temperature_c),
                    None
                    if not hasattr(record, "relative_humidity_pct") or pd.isna(record.relative_humidity_pct)
                    else float(record.relative_humidity_pct),
                    None
                    if not hasattr(record, "wind_speed_m_s") or pd.isna(record.wind_speed_m_s)
                    else float(record.wind_speed_m_s),
                    sources,
                )
            )
        connection.executemany(
            """
            INSERT INTO hydrology_daily (
                township_id, observed_on, rainfall_mm, discharge_m3_s, chirps_rainfall_mm,
                soil_moisture, runoff, temperature_c, relative_humidity_pct, wind_speed_m_s, sources_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(township_id, observed_on) DO UPDATE SET
                rainfall_mm=excluded.rainfall_mm,
                discharge_m3_s=excluded.discharge_m3_s,
                temperature_c=COALESCE(excluded.temperature_c, hydrology_daily.temperature_c),
                relative_humidity_pct=COALESCE(
                    excluded.relative_humidity_pct, hydrology_daily.relative_humidity_pct
                ),
                wind_speed_m_s=COALESCE(excluded.wind_speed_m_s, hydrology_daily.wind_speed_m_s),
                sources_json=excluded.sources_json
            """,
            batch,
        )
        saved += len(batch)
        print(f"hydrology {path.name} {len(batch)}", flush=True)
    return saved


def _get(url: str, timeout: float = 25.0):
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _polygon(latitude: float, longitude: float) -> str:
    delta = 0.05
    ring = [
        [longitude - delta, latitude - delta],
        [longitude + delta, latitude - delta],
        [longitude + delta, latitude + delta],
        [longitude - delta, latitude + delta],
        [longitude - delta, latitude - delta],
    ]
    return json.dumps({"type": "Polygon", "coordinates": [ring]})


def _chirps_chunk(
    township_id: str, latitude: float, longitude: float, start: date, end: date
) -> list[tuple[str, str, float]]:
    query = urllib.parse.urlencode(
        {
            "datatype": 0,
            "begintime": start.strftime("%m/%d/%Y"),
            "endtime": end.strftime("%m/%d/%Y"),
            "intervaltype": 0,
            "operationtype": 5,
            "geometry": _polygon(latitude, longitude),
        }
    )
    submitted = _get(f"https://climateserv.servirglobal.net/api/submitDataRequest/?{query}", timeout=40)
    request_id = submitted if isinstance(submitted, str) else submitted.get("id") or submitted.get("requestId")
    if not request_id:
        raise RuntimeError(f"CHIRPS submit failed: {submitted}")
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        progress = _get(
            "https://climateserv.servirglobal.net/api/getDataRequestProgress/?id="
            + urllib.parse.quote(str(request_id))
        )
        percent = progress if isinstance(progress, (int, float)) else progress.get("progress", 0)
        if float(percent) >= 100:
            break
        time.sleep(2)
    payload = _get(
        "https://climateserv.servirglobal.net/api/getDataFromRequest/?id="
        + urllib.parse.quote(str(request_id)),
        timeout=60,
    )
    rows = payload if isinstance(payload, list) else payload.get("data", [])
    stored: list[tuple[str, str, float]] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        raw_date = str(item.get("date") or item.get("datetime") or "")[:10]
        value = item.get("value", item.get("avg"))
        if not raw_date or value is None or float(value) < 0:
            continue
        stored.append((township_id, raw_date, float(value)))
    return stored


def _store_chirps(connection: sqlite3.Connection, places: pd.DataFrame, *, full: bool) -> tuple[int, str]:
    saved = 0
    errors: list[str] = []
    end = date.today()
    start = CHIRPS_RANGE_START if full else date(end.year, 1, 1)
    for row in places.itertuples(index=False):
        township_id = _slug(str(row.township))
        cursor = start
        while cursor <= end:
            chunk_end = min(end, cursor + timedelta(days=120))
            try:
                series = _chirps_chunk(
                    township_id, float(row.weather_latitude), float(row.weather_longitude), cursor, chunk_end
                )
            except Exception as exc:
                errors.append(f"{row.township} {cursor}: {exc}")
                break
            connection.executemany(
                """
                INSERT INTO chirps_daily (township_id, observed_on, rainfall_mm)
                VALUES (?, ?, ?)
                ON CONFLICT(township_id, observed_on) DO UPDATE SET rainfall_mm=excluded.rainfall_mm
                """,
                series,
            )
            for township, day, rain in series:
                connection.execute(
                    """
                    UPDATE hydrology_daily SET chirps_rainfall_mm=?
                    WHERE township_id=? AND observed_on=?
                    """,
                    (rain, township, day),
                )
            connection.commit()
            saved += len(series)
            cursor = chunk_end + timedelta(days=1)
            print(f"chirps {row.township} {cursor} ({len(series)})", flush=True)
    status = "ready" if saved and not errors else "partial" if saved else "unavailable"
    return saved, status + ("" if not errors else "; " + " | ".join(errors[:3]))


def _store_cems_glofas(connection: sqlite3.Connection, places: pd.DataFrame) -> tuple[int, str]:
    from app.services.copernicus_glofas import fetch_ensemble_forecast, fetch_historical_point_series

    saved = 0
    end = date.today()
    start = max(APP_HISTORY_START, date(end.year - 3, 1, 1))
    for row in places.itertuples(index=False):
        township_id = _slug(str(row.township))
        lat = float(row.river_latitude)
        lon = float(row.river_longitude)
        history = fetch_historical_point_series(lat, lon, start, end)
        batch: list[tuple] = []
        for item in history:
            day = str(item["date"])[:10]
            batch.append(
                (
                    township_id,
                    day,
                    None,
                    item.get("discharge_m3_s"),
                    None,
                    item.get("soil_moisture"),
                    item.get("runoff"),
                    None,
                    None,
                    None,
                    json.dumps({"discharge": "cems-glofas-historical", "soil": "cems-glofas-historical"}),
                )
            )
        connection.executemany(
            """
            INSERT INTO hydrology_daily (
                township_id, observed_on, rainfall_mm, discharge_m3_s, chirps_rainfall_mm,
                soil_moisture, runoff, temperature_c, relative_humidity_pct, wind_speed_m_s, sources_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(township_id, observed_on) DO UPDATE SET
                discharge_m3_s=COALESCE(excluded.discharge_m3_s, hydrology_daily.discharge_m3_s),
                soil_moisture=COALESCE(excluded.soil_moisture, hydrology_daily.soil_moisture),
                runoff=COALESCE(excluded.runoff, hydrology_daily.runoff),
                sources_json=excluded.sources_json
            """,
            batch,
        )
        saved += len(batch)
        forecast = fetch_ensemble_forecast(lat, lon, horizon_days=30)
        fetched = date.today().isoformat()
        frows = [
            (
                township_id,
                item["target_date"],
                int(item["lead_days"]),
                None,
                item.get("discharge_m3_s"),
                None,
                item.get("source", "cems-glofas-ensemble"),
                fetched,
            )
            for item in forecast
        ]
        connection.executemany(
            """
            INSERT INTO glofas_forecast_daily (
                township_id, target_date, lead_days, rainfall_mm, discharge_m3_s,
                soil_moisture, source, fetched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(township_id, target_date, lead_days, source) DO UPDATE SET
                discharge_m3_s=excluded.discharge_m3_s,
                fetched_at=excluded.fetched_at
            """,
            frows,
        )
        saved += len(frows)
    status = "ready" if saved else "skipped"
    return saved, status


def _store_live(connection: sqlite3.Connection, places: pd.DataFrame) -> int:
    fetched = date.today().isoformat()
    saved = 0
    for row in places.itertuples(index=False):
        township_id = _slug(str(row.township))
        latitude = float(row.weather_latitude)
        longitude = float(row.weather_longitude)
        weather = _get(
            "https://api.open-meteo.com/v1/forecast?"
            + urllib.parse.urlencode(
                {
                    "latitude": latitude,
                    "longitude": longitude,
                    "daily": "precipitation_sum",
                    "forecast_days": 7,
                    "timezone": "Asia/Yangon",
                }
            )
        )
        flood = _get(
            "https://flood-api.open-meteo.com/v1/flood?"
            + urllib.parse.urlencode(
                {
                    "latitude": float(row.river_latitude),
                    "longitude": float(row.river_longitude),
                    "daily": "river_discharge",
                    "forecast_days": 7,
                    "timezone": "GMT",
                }
            )
        )
        rain_days = weather.get("daily", {}).get("time", [])
        rain_values = weather.get("daily", {}).get("precipitation_sum", [])
        flow_days = flood.get("daily", {}).get("time", [])
        flow_values = flood.get("daily", {}).get("river_discharge", [])
        rows = []
        for day, value in zip(rain_days, rain_values):
            rows.append((township_id, day, None if value is None else float(value), None, "open-meteo-forecast", fetched))
        for day, value in zip(flow_days, flow_values):
            rows.append((township_id, day, None, None if value is None else float(value), "open-meteo-flood", fetched))
        connection.executemany(
            """
            INSERT INTO live_forecast (township_id, target_date, rainfall_mm, discharge_m3_s, source, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(township_id, target_date, source) DO UPDATE SET
                rainfall_mm=excluded.rainfall_mm,
                discharge_m3_s=excluded.discharge_m3_s,
                fetched_at=excluded.fetched_at
            """,
            rows,
        )
        saved += len(rows)
    return saved


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true", help="Alias for --chirps --cems")
    parser.add_argument("--chirps", action="store_true", help="Fetch CHIRPS from ClimateSERV (slow)")
    parser.add_argument("--cems", action="store_true", help="Fetch CEMS GloFAS historical/ensemble when CDS configured")
    args = parser.parse_args()
    if args.full:
        args.chirps = True
        args.cems = True
    places = pd.read_csv(RIVER_POINTS)
    connection = _connect()
    history_rows = _store_history(connection)
    _catalog(connection, "validated_daily", "historical", "ready", f"{history_rows} township-days")
    merged_rows = _store_hydrology_from_merged(connection)
    _catalog(connection, "hydro_merged", "historical", "ready", f"{merged_rows} hydrology_daily rows")
    live_rows = _store_live(connection, places)
    _catalog(connection, "open-meteo-forecast-and-flood", "future", "ready", f"{live_rows} forecast rows")
    chirps_rows, chirps_detail = (0, "skipped")
    if args.chirps:
        chirps_rows, chirps_detail = _store_chirps(connection, places, full=True)
    _catalog(connection, "chirps-v3-climateserv", "historical", chirps_detail.split(";")[0], f"{chirps_rows} days")
    cems_rows, cems_detail = (0, "skipped")
    if args.cems:
        cems_rows, cems_detail = _store_cems_glofas(connection, places)
    _catalog(connection, "cems-glofas", "historical+forecast", cems_detail, f"{cems_rows} rows")
    _catalog(
        connection,
        "static_rasters",
        "static",
        "run ml/flood/ingest_rasters.py",
        "JRC hazard, HAND, HydroBASINS, WorldCover under data/external/rasters/",
    )
    connection.commit()
    print(
        json.dumps(
            {
                "database": str(DB_PATH),
                "history": history_rows,
                "hydrology_merged": merged_rows,
                "live": live_rows,
                "chirps": chirps_rows,
                "cems_glofas": cems_rows,
            }
        )
    )


if __name__ == "__main__":
    main()
