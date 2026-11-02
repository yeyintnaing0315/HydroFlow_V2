"""Local paths and township coordinates for Open-Meteo / NASA POWER / GloFAS caches."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[3]
RIVER_POINTS_CSV = PROJECT_ROOT / "data" / "external" / "bago_river_points.csv"
VALIDATED_DAILY_CSV = PROJECT_ROOT / "data" / "processed" / "validated_daily.csv"

OPEN_METEO_ARCHIVE_DIR = PROJECT_ROOT / "data" / "external" / "open_meteo_archive_daily"
GLOFAS_DISCHARGE_DIR = PROJECT_ROOT / "data" / "external" / "glofas_discharge"
NASA_POWER_HYDRO_DIR = PROJECT_ROOT / "data" / "external" / "nasa_power_hydro"
HYDRO_MERGED_DIR = PROJECT_ROOT / "data" / "external" / "hydro_merged"


def township_slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.strip().lower())
    return slug.strip("_")


@dataclass(frozen=True)
class HydroLocation:
    township_id: str
    township: str
    weather_latitude: float
    weather_longitude: float
    river_latitude: float
    river_longitude: float
    cache_key: str | None = None

    @property
    def storage_id(self) -> str:
        return self.cache_key or self.township_id


@lru_cache(maxsize=1)
def download_locations() -> tuple[HydroLocation, ...]:
    """All townships with coordinates (river CSV first, validated daily fills gaps)."""
    by_id: dict[str, HydroLocation] = {}
    if RIVER_POINTS_CSV.is_file():
        with RIVER_POINTS_CSV.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                township_id = township_slug(row["township"])
                by_id[township_id] = HydroLocation(
                    township_id=township_id,
                    township=row["township"],
                    weather_latitude=float(row["weather_latitude"]),
                    weather_longitude=float(row["weather_longitude"]),
                    river_latitude=float(row["river_latitude"]),
                    river_longitude=float(row["river_longitude"]),
                )
    if VALIDATED_DAILY_CSV.is_file():
        frame = pd.read_csv(
            VALIDATED_DAILY_CSV,
            usecols=["township_id", "township", "lat", "lng"],
        )
        grouped = frame.groupby("township_id", as_index=False).first()
        for record in grouped.itertuples(index=False):
            township_id = str(record.township_id)
            if township_id in by_id:
                continue
            lat = float(record.lat)
            lng = float(record.lng)
            by_id[township_id] = HydroLocation(
                township_id=township_id,
                township=str(record.township),
                weather_latitude=lat,
                weather_longitude=lng,
                river_latitude=lat,
                river_longitude=lng,
            )
    return tuple(sorted(by_id.values(), key=lambda item: item.township_id))


async def all_download_locations() -> tuple[HydroLocation, ...]:
    """Validated/river slugs plus every Bago township from Open Admin (28 in UI)."""
    by_id = {loc.township_id: loc for loc in download_locations()}
    try:
        from app.services.open_admin_areas import bago_areas

        payload = await bago_areas()
        for district in payload.get("districts", []):
            for township in district.get("townships", []):
                admin_id = str(township["id"])
                if admin_id in by_id:
                    continue
                lat = float(township["latitude"])
                lng = float(township["longitude"])
                by_id[admin_id] = HydroLocation(
                    township_id=admin_id,
                    township=str(township["name_en"]),
                    weather_latitude=lat,
                    weather_longitude=lng,
                    river_latitude=lat,
                    river_longitude=lng,
                    cache_key=admin_id,
                )
    except Exception:
        pass
    return tuple(sorted(by_id.values(), key=lambda item: item.township))


def merged_series_path(township_id: str) -> Path:
    return HYDRO_MERGED_DIR / f"{township_id}.csv"
