import pandas as pd
from pandas.testing import assert_frame_equal

from hydroflow_ml.config import MODEL_FEATURES
from hydroflow_ml.features import engineer_features


def history() -> pd.DataFrame:
    rows = []
    for township, offset in (("a", 0), ("b", 10)):
        for day in range(8):
            rows.append(
                {
                    "date": pd.Timestamp("2024-01-01") + pd.Timedelta(days=day),
                    "rainfall_mm": float(day + offset),
                    "river_discharge_m3s": float(2 * day + offset),
                    "township_id": township,
                    "township": township.upper(),
                    "lat": 17.0,
                    "lng": 96.0,
                    "households": None,
                    "affected_people": None,
                    "flood": 0,
                }
            )
    return pd.DataFrame(rows)


def test_features_are_deterministic_and_exclude_impact_fields():
    first = engineer_features(history())
    second = engineer_features(history())
    assert_frame_equal(first, second)
    assert "households" not in MODEL_FEATURES
    assert "affected_people" not in MODEL_FEATURES


def test_future_changes_cannot_change_past_features():
    original = history()
    changed = original.copy()
    changed.loc[changed["date"] >= "2024-01-06", "rainfall_mm"] = 99999.0
    changed.loc[changed["date"] >= "2024-01-06", "river_discharge_m3s"] = 99999.0

    before = engineer_features(original)
    after = engineer_features(changed)
    past = before["date"] < "2024-01-06"
    assert_frame_equal(
        before.loc[past, list(MODEL_FEATURES)].reset_index(drop=True),
        after.loc[past, list(MODEL_FEATURES)].reset_index(drop=True),
    )


def test_trailing_features_use_expected_history():
    features = engineer_features(history())
    township_a = features[features["township_id"] == "a"].reset_index(drop=True)
    assert township_a.loc[2, "rainfall_3d_mm"] == 3.0
    assert township_a.loc[3, "rainfall_3d_mm"] == 6.0
    assert township_a.loc[3, "rainfall_lag_1d_mm"] == 2.0
