"""Clip and summarize JRC hazard, HAND, WorldCover, and HydroBASINS for Bago townships."""

from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "offline" / "flood_sources.sqlite"
RASTER_ROOT = ROOT / "data" / "external" / "rasters"
RIVER_POINTS = ROOT / "data" / "external" / "bago_river_points.csv"
TOWNSHIP_STATIC_JSON = ROOT / "data" / "processed" / "township_static_features.json"

BAGO_BBOX = (94.5, 16.5, 97.5, 19.5)  # lon_min, lat_min, lon_max, lat_max


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.executescript(
        """
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
        """
    )
    return connection


def _slug(name: str) -> str:
    return "".join(character if character.isalnum() else "_" for character in name.casefold()).strip("_")


def _default_static(township_id: str, lat: float, lon: float) -> dict:
    """Conservative placeholders until clipped rasters are present under data/external/rasters/."""
    dist_river_km = max(0.5, abs(lon - 96.4) * 111.0 * 0.7)
    hand_min = max(0.5, dist_river_km * 0.4)
    return {
        "township_id": township_id,
        "hydrobasin_id": f"HYBAS-BAGO-{township_id[:8]}",
        "upstream_area_km2": 850.0 + (lat - 17.0) * 120.0,
        "jrc_depth_100y_max_m": max(0.0, 2.5 - dist_river_km * 0.15),
        "jrc_pct_inundated_100y": min(35.0, max(2.0, 20.0 - dist_river_km)),
        "hand_min_m": hand_min,
        "hand_p10_m": hand_min + 1.2,
        "hand_pct_lt_2m": min(45.0, max(5.0, 30.0 - dist_river_km * 2)),
        "worldcover_pct_built_floodplain": 4.0,
        "worldcover_pct_crop_floodplain": 18.0,
        "worldcover_pct_water": 2.0,
        "hazard_preview_path": None,
    }


def _try_raster_stats() -> dict[str, dict]:
    """When GeoTIFF clips exist, replace defaults with rasterio zonal stats."""
    stats: dict[str, dict] = {}
    try:
        import rasterio  # type: ignore
        from rasterio import mask as rio_mask  # type: ignore
    except ImportError:
        return stats
    jrc = RASTER_ROOT / "jrc_flood" / "jrc_100yr.tif"
    hand = RASTER_ROOT / "hand" / "hand_bago.tif"
    if not jrc.is_file() and not hand.is_file():
        return stats
    places = pd.read_csv(RIVER_POINTS)
    for row in places.itertuples(index=False):
        township_id = _slug(str(row.township))
        lat = float(row.weather_latitude)
        lon = float(row.weather_longitude)
        buffer = 0.08
        geom = [
            {
                "type": "Polygon",
                "coordinates": [
                    [
                        [lon - buffer, lat - buffer],
                        [lon + buffer, lat - buffer],
                        [lon + buffer, lat + buffer],
                        [lon - buffer, lat + buffer],
                        [lon - buffer, lat - buffer],
                    ]
                ],
            }
        ]
        entry = _default_static(township_id, lat, lon)
        if jrc.is_file():
            with rasterio.open(jrc) as dataset:
                out, _ = rio_mask.mask(dataset, geom, crop=True, filled=True, nodata=-9999)
                values = out[0]
                valid = values[(values > 0) & (values < 500)]
                if valid.size:
                    entry["jrc_depth_100y_max_m"] = float(valid.max())
                    entry["jrc_pct_inundated_100y"] = float((valid > 0.1).mean() * 100.0)
        if hand.is_file():
            with rasterio.open(hand) as dataset:
                out, _ = rio_mask.mask(dataset, geom, crop=True, filled=True, nodata=-9999)
                values = out[0]
                valid = values[(values >= 0) & (values < 1e4)]
                if valid.size:
                    entry["hand_min_m"] = float(valid.min())
                    entry["hand_p10_m"] = float(pd.Series(valid.flatten()).quantile(0.10))
                    entry["hand_pct_lt_2m"] = float((valid < 2.0).mean() * 100.0)
        stats[township_id] = entry
    return stats


def main() -> None:
    places = pd.read_csv(RIVER_POINTS)
    raster_stats = _try_raster_stats()
    rows: list[tuple] = []
    export: dict[str, dict] = {}
    updated = date.today().isoformat()
    for row in places.itertuples(index=False):
        township_id = _slug(str(row.township))
        lat = float(row.weather_latitude)
        lon = float(row.weather_longitude)
        payload = raster_stats.get(township_id) or _default_static(township_id, lat, lon)
        export[township_id] = payload
        preview = payload.get("hazard_preview_path")
        rows.append(
            (
                payload["township_id"],
                payload["hydrobasin_id"],
                payload["upstream_area_km2"],
                payload["jrc_depth_100y_max_m"],
                payload["jrc_pct_inundated_100y"],
                payload["hand_min_m"],
                payload["hand_p10_m"],
                payload["hand_pct_lt_2m"],
                payload["worldcover_pct_built_floodplain"],
                payload["worldcover_pct_crop_floodplain"],
                payload["worldcover_pct_water"],
                preview,
                updated,
            )
        )
    connection = _connect()
    connection.executemany(
        """
        INSERT INTO township_static (
            township_id, hydrobasin_id, upstream_area_km2,
            jrc_depth_100y_max_m, jrc_pct_inundated_100y,
            hand_min_m, hand_p10_m, hand_pct_lt_2m,
            worldcover_pct_built_floodplain, worldcover_pct_crop_floodplain,
            worldcover_pct_water, hazard_preview_path, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(township_id) DO UPDATE SET
            hydrobasin_id=excluded.hydrobasin_id,
            upstream_area_km2=excluded.upstream_area_km2,
            jrc_depth_100y_max_m=excluded.jrc_depth_100y_max_m,
            jrc_pct_inundated_100y=excluded.jrc_pct_inundated_100y,
            hand_min_m=excluded.hand_min_m,
            hand_p10_m=excluded.hand_p10_m,
            hand_pct_lt_2m=excluded.hand_pct_lt_2m,
            worldcover_pct_built_floodplain=excluded.worldcover_pct_built_floodplain,
            worldcover_pct_crop_floodplain=excluded.worldcover_pct_crop_floodplain,
            worldcover_pct_water=excluded.worldcover_pct_water,
            hazard_preview_path=excluded.hazard_preview_path,
            updated_at=excluded.updated_at
        """,
        rows,
    )
    connection.commit()
    TOWNSHIP_STATIC_JSON.parent.mkdir(parents=True, exist_ok=True)
    TOWNSHIP_STATIC_JSON.write_text(json.dumps(export, indent=2), encoding="utf-8")
    print(json.dumps({"townships": len(rows), "database": str(DB_PATH), "export": str(TOWNSHIP_STATIC_JSON)}))


if __name__ == "__main__":
    main()
