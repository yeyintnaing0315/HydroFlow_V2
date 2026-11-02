from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

from .config import PROJECT_ROOT

CACHE_DIR = PROJECT_ROOT / "data" / "external" / "nasa_power"
DAILY_PATH = PROJECT_ROOT / "data" / "external" / "nasa_power_daily.csv"
POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
PARAMETERS = ("GWETROOT", "RH2M")


def _request(latitude: float, longitude: float, start: str, end: str) -> dict:
    query = urllib.parse.urlencode(
        {
            "parameters": ",".join(PARAMETERS),
            "community": "AG",
            "longitude": longitude,
            "latitude": latitude,
            "start": start,
            "end": end,
            "format": "JSON",
            "time-standard": "UTC",
        }
    )
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(f"{POWER_URL}?{query}", timeout=90) as response:
                return json.load(response)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"NASA POWER request failed for {latitude}, {longitude}") from last_error


def download_township_series(
    locations: pd.DataFrame, start: str, end: str, pause_seconds: float = 1.0
) -> pd.DataFrame:
    """Download daily root-zone wetness and humidity. -999 values are omitted."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    frames = []
    for row in locations.itertuples(index=False):
        cache = CACHE_DIR / f"{row.township_id}.json"
        if cache.exists():
            payload = json.loads(cache.read_text(encoding="utf-8"))
        else:
            payload = _request(float(row.lat), float(row.lng), start, end)
            cache.write_text(json.dumps(payload), encoding="utf-8")
            time.sleep(pause_seconds)
        values = payload["properties"]["parameter"]
        wetness = values["GWETROOT"]
        humidity = values["RH2M"]
        days = sorted(set(wetness) & set(humidity))
        frames.append(
            pd.DataFrame(
                {
                    "township_id": row.township_id,
                    "date": pd.to_datetime(days, format="%Y%m%d"),
                    "soil_wetness_root": [wetness[day] for day in days],
                    "relative_humidity_pct": [humidity[day] for day in days],
                }
            )
        )
    frame = pd.concat(frames, ignore_index=True)
    frame = frame[(frame["soil_wetness_root"] != -999) & (frame["relative_humidity_pct"] != -999)]
    DAILY_PATH.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(DAILY_PATH, index=False, date_format="%Y-%m-%d")
    return frame
