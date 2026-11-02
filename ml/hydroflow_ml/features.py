from __future__ import annotations

import numpy as np
import pandas as pd

from .config import FEATURE_DATA, IMPACT_COLUMNS, MODEL_FEATURES
from .validation import validate_daily_data


def engineer_features(data: pd.DataFrame) -> pd.DataFrame:
    """Create same-day and trailing features using only information at or before each row."""
    validate_daily_data(data)
    frame = data.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    frame = frame.sort_values(["township_id", "date"], kind="stable").reset_index(drop=True)
    grouped = frame.groupby("township_id", sort=False, group_keys=False)

    rain = grouped["rainfall_mm"]
    discharge = grouped["river_discharge_m3s"]
    frame["rainfall_3d_mm"] = rain.transform(lambda s: s.rolling(3, min_periods=1).sum())
    frame["rainfall_7d_mm"] = rain.transform(lambda s: s.rolling(7, min_periods=1).sum())
    frame["rainfall_lag_1d_mm"] = rain.shift(1).fillna(0.0)
    frame["discharge_lag_1d_m3s"] = discharge.shift(1).fillna(0.0)
    frame["discharge_delta_1d_m3s"] = (
        frame["river_discharge_m3s"] - frame["discharge_lag_1d_m3s"]
    )
    frame["discharge_3d_mean_m3s"] = discharge.transform(
        lambda s: s.rolling(3, min_periods=1).mean()
    )
    day = frame["date"].dt.dayofyear
    frame["day_of_year_sin"] = np.sin(2 * np.pi * day / 365.25)
    frame["day_of_year_cos"] = np.cos(2 * np.pi * day / 365.25)

    forbidden = set(IMPACT_COLUMNS) & set(MODEL_FEATURES)
    if forbidden:
        raise RuntimeError(f"Impact leakage columns entered MODEL_FEATURES: {sorted(forbidden)}")
    return frame.sort_values(["date", "township_id"], kind="stable").reset_index(drop=True)


def build_feature_data(data: pd.DataFrame, destination=FEATURE_DATA) -> pd.DataFrame:
    frame = engineer_features(data)
    destination.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(destination, index=False, date_format="%Y-%m-%d")
    return frame
