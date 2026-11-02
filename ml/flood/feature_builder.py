"""Join labeled daily rows with offline hydrology extras and static raster features."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.hydro_offline_db import static_features  # noqa: E402

DAILY_PATH = ROOT / "data" / "processed" / "validated_daily.csv"
STATIC_JSON = ROOT / "data" / "processed" / "township_static_features.json"
DB_PATH = ROOT / "data" / "offline" / "flood_sources.sqlite"

BASE_FEATURES = (
    "rainfall_1d_mm",
    "rainfall_3d_mm",
    "rainfall_7d_mm",
    "rainfall_14d_mm",
    "rainfall_30d_mm",
    "temperature_c",
    "relative_humidity_pct",
    "wind_speed_m_s",
    "latitude",
    "longitude",
    "day_of_year_sin",
    "day_of_year_cos",
    "discharge_lag_1d_m3s",
    "discharge_lag_3d_mean_m3s",
)

EXTENDED_FEATURES = (
    "soil_moisture",
    "runoff",
    "chirps_rainfall_7d_mm",
    "hand_pct_lt_2m",
    "jrc_depth_100y_max_m",
    "worldcover_pct_built_floodplain",
)


def _static_for(township_id: str) -> dict[str, float]:
    payload = static_features(township_id)
    if payload:
        return {key: float(value) for key, value in payload.items() if isinstance(value, (int, float))}
    if STATIC_JSON.is_file():
        data = json.loads(STATIC_JSON.read_text(encoding="utf-8"))
        entry = data.get(township_id) or data.get(township_id.replace("-", "_"))
        if isinstance(entry, dict):
            return {key: float(value) for key, value in entry.items() if isinstance(value, (int, float))}
    return {}


def load_offline_extras(township_id: str, start: str, end: str) -> pd.DataFrame:
    if not DB_PATH.is_file():
        return pd.DataFrame()
    import sqlite3

    connection = sqlite3.connect(DB_PATH)
    frame = pd.read_sql_query(
        """
        SELECT observed_on AS date, chirps_rainfall_mm, soil_moisture, runoff
        FROM hydrology_daily
        WHERE township_id = ? AND observed_on >= ? AND observed_on <= ?
        ORDER BY observed_on
        """,
        connection,
        params=(township_id, start, end),
    )
    connection.close()
    if frame.empty:
        return frame
    frame["date"] = pd.to_datetime(frame["date"])
    chirps = frame["chirps_rainfall_mm"]
    frame["chirps_rainfall_7d_mm"] = chirps.rolling(7, min_periods=7).sum()
    return frame


def enrich_labeled_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Attach static and offline columns; keep base features intact for the served model."""
    if frame.empty:
        return frame
    static_by_id = {tid: _static_for(str(tid)) for tid in frame["township_id"].unique()}
    extras = []
    for tid in frame["township_id"].unique():
        subset = frame.loc[frame["township_id"] == tid]
        start = subset["date"].min().strftime("%Y-%m-%d")
        end = subset["date"].max().strftime("%Y-%m-%d")
        offline = load_offline_extras(str(tid), start, end)
        if offline.empty:
            continue
        offline["township_id"] = tid
        extras.append(offline)
    if extras:
        merged = pd.concat(extras, ignore_index=True)
        frame = frame.merge(merged, on=["township_id", "date"], how="left")
    for column in EXTENDED_FEATURES:
        if column not in frame.columns:
            frame[column] = None
    for index, tid in enumerate(frame["township_id"].unique()):
        if index > 0 and tid in static_by_id:
            pass
    for tid, values in static_by_id.items():
        mask = frame["township_id"] == tid
        for key, value in values.items():
            col = key if key in EXTENDED_FEATURES else None
            if col:
                frame.loc[mask, col] = value
    return frame
