"""Download Open-Meteo archive, GloFAS discharge, and NASA POWER to data/external/."""

from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path

import pandas as pd

from app.services import clients
from app.services.hydro_history import GLOFAS_DISCHARGE_START, NASA_POWER_START
from app.services.hydro_sources import (
    GLOFAS_DISCHARGE_DIR,
    HYDRO_MERGED_DIR,
    NASA_POWER_HYDRO_DIR,
    OPEN_METEO_ARCHIVE_DIR,
    HydroLocation,
    all_download_locations,
    download_locations,
)


def _write_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, date_format="%Y-%m-%d")


async def download_township_series(
    location: HydroLocation,
    start: date,
    end: date,
    *,
    skip_existing: bool = False,
) -> Path:
    """Fetch all three providers and write per-source CSVs plus one merged file."""
    storage_id = location.storage_id
    meteo_path = OPEN_METEO_ARCHIVE_DIR / f"{storage_id}.csv"
    glofas_path = GLOFAS_DISCHARGE_DIR / f"{storage_id}.csv"
    nasa_path = NASA_POWER_HYDRO_DIR / f"{storage_id}.csv"
    merged_path = HYDRO_MERGED_DIR / f"{storage_id}.csv"

    if skip_existing and merged_path.is_file():
        return merged_path

    weather = await clients.open_meteo_archive_daily_weather(
        location.weather_latitude,
        location.weather_longitude,
        start,
        end,
    )
    meteo_frame = pd.DataFrame(
        {
            "date": [row["date"] for row in weather],
            "precipitation_mm": [row["rainfall_mm"] for row in weather],
            "temperature_c": [row["temperature_c"] for row in weather],
            "relative_humidity_pct": [row["relative_humidity_pct"] for row in weather],
            "wind_speed_m_s": [row["wind_speed_m_s"] for row in weather],
        }
    )
    _write_csv(meteo_path, meteo_frame)

    discharge = await clients.glofas_discharge_daily_range(
        location.river_latitude,
        location.river_longitude,
        max(start, GLOFAS_DISCHARGE_START),
        end,
    )
    glofas_frame = pd.DataFrame(
        {"date": [day for day, _ in discharge], "river_discharge_m3s": [value for _, value in discharge]}
    )
    _write_csv(glofas_path, glofas_frame)

    nasa_start = max(start, NASA_POWER_START)
    nasa_points = await clients.nasa_power_history_range(
        location.weather_latitude,
        location.weather_longitude,
        nasa_start,
        end,
    )
    nasa_frame = pd.DataFrame(
        {
            "date": [point.date for point in nasa_points],
            "precipitation_mm": [point.precipitation_mm for point in nasa_points],
            "temperature_c": [point.temperature_c for point in nasa_points],
            "relative_humidity_pct": [point.relative_humidity_pct for point in nasa_points],
            "wind_speed_m_s": [point.wind_speed_m_s for point in nasa_points],
        }
    )
    _write_csv(nasa_path, nasa_frame)

    merged = meteo_frame.merge(glofas_frame, on="date", how="inner")
    if not nasa_frame.empty:
        merged = merged.merge(nasa_frame, on="date", how="left", suffixes=("", "_nasa"))
        for column in ("precipitation_mm", "temperature_c", "relative_humidity_pct", "wind_speed_m_s"):
            nasa_col = f"{column}_nasa"
            if nasa_col in merged.columns:
                merged[column] = merged[column].fillna(merged[nasa_col])
                merged = merged.drop(columns=[nasa_col])
    merged["rainfall_mm"] = merged["precipitation_mm"]
    merged["township_id"] = location.township_id
    merged["township"] = location.township
    _write_csv(merged_path, merged)
    return merged_path


async def download_all_townships(
    start: date,
    end: date,
    *,
    skip_existing: bool = False,
    township_ids: set[str] | None = None,
) -> list[Path]:
    locations = await all_download_locations()
    if township_ids:
        locations = [
            loc
            for loc in locations
            if loc.township_id in township_ids or loc.storage_id in township_ids
        ]
    paths: list[Path] = []
    for location in locations:
        paths.append(
            await download_township_series(location, start, end, skip_existing=skip_existing)
        )
        await asyncio.sleep(0.5)
    return paths


def _parse_cli_date(raw: str) -> date:
    return date.fromisoformat(raw.strip())


async def _cli_main() -> None:
    import argparse
    import json

    from app.services.hydro_history import APP_HISTORY_START

    parser = argparse.ArgumentParser(description="Download Open-Meteo, GloFAS, and NASA POWER caches.")
    parser.add_argument("--start", default=APP_HISTORY_START.isoformat())
    parser.add_argument("--end", default=date.today().isoformat())
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--township-id", action="append", dest="township_ids")
    args = parser.parse_args()
    start = _parse_cli_date(args.start)
    end = _parse_cli_date(args.end)
    ids = set(args.township_ids) if args.township_ids else None
    paths = await download_all_townships(start, end, skip_existing=args.skip_existing, township_ids=ids)
    print(json.dumps({"files": len(paths), "start": start.isoformat(), "end": end.isoformat()}))


if __name__ == "__main__":
    asyncio.run(_cli_main())
