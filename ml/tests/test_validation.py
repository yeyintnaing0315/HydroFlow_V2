import pandas as pd
import pytest

from hydroflow_ml.validation import DataValidationError, validate_daily_data


def valid_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": ["2024-01-01", "2024-01-02"],
            "rainfall_mm": [0.0, 2.0],
            "river_discharge_m3s": [1.0, 1.2],
            "township_id": ["a", "a"],
            "township": ["A", "A"],
            "lat": [17.0, 17.0],
            "lng": [96.0, 96.0],
            "households": [None, 10],
            "affected_people": [None, 20],
            "flood": [0, 1],
        }
    )


def test_valid_data_has_deterministic_report():
    report = validate_daily_data(valid_frame())
    assert report.rows == 2
    assert report.flood_rows == 1
    assert report.non_flood_rows == 1
    assert report.flood_rate == 0.5
    assert report.townships_with_flood == 1
    assert report.min_rows_per_township == 2
    assert report.max_rows_per_township == 2
    assert report.start_date == "2024-01-01"


def test_duplicate_township_date_is_rejected():
    data = valid_frame()
    data.loc[1, "date"] = data.loc[0, "date"]
    with pytest.raises(DataValidationError, match="Duplicate"):
        validate_daily_data(data)


def test_non_binary_target_is_rejected():
    data = valid_frame()
    data.loc[1, "flood"] = 2
    with pytest.raises(DataValidationError, match="binary"):
        validate_daily_data(data)
