import pandas as pd
import pytest

from hydroflow_ml.config import MODEL_FEATURES


def synthetic_features() -> pd.DataFrame:
    """Small chronological frame with both classes in train, validation, and test."""
    dates = pd.date_range("2024-01-01", periods=30, freq="D")
    rows = []
    for day_index, day in enumerate(dates):
        for township_index, township in enumerate(("a", "b")):
            flood = int((day_index + township_index) % 5 == 0)
            rainfall = 40.0 if flood else 1.0
            discharge = 100.0 if flood else 2.0
            rows.append(
                {
                    "date": day,
                    "township_id": township,
                    "flood": flood,
                    "rainfall_mm": rainfall,
                    "river_discharge_m3s": discharge,
                    "rainfall_3d_mm": rainfall,
                    "rainfall_7d_mm": rainfall,
                    "rainfall_lag_1d_mm": 0.0,
                    "discharge_lag_1d_m3s": 0.0,
                    "discharge_delta_1d_m3s": 0.0,
                    "discharge_3d_mean_m3s": discharge,
                    "day_of_year_sin": 0.1 * township_index,
                    "day_of_year_cos": 0.9,
                    "lat": 17.0 + township_index,
                    "lng": 96.0,
                }
            )
    frame = pd.DataFrame(rows)
    missing = set(MODEL_FEATURES) - set(frame.columns)
    if missing:
        raise RuntimeError(f"Synthetic frame is missing {sorted(missing)}")
    return frame


@pytest.fixture
def feature_frame() -> pd.DataFrame:
    return synthetic_features()
