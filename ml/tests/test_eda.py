import json

import pandas as pd
import pytest

from hydroflow_ml.config import RAW_DATA
from hydroflow_ml.eda import create_eda_summary
from hydroflow_ml.ingest import load_raw
from hydroflow_ml.validation import validate_daily_data


def sample() -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=5, freq="D")
    floods = {
        "a": [1, 1, 0, 0, 1],
        "b": [0, 0, 0, 1, 0],
        "c": [0, 0, 0, 0, 0],
    }
    rows = []
    for township, labels in floods.items():
        for day, label in zip(dates, labels):
            rows.append(
                {
                    "date": day,
                    "rainfall_mm": 1.0,
                    "river_discharge_m3s": 2.0,
                    "township_id": township,
                    "flood": label,
                }
            )
    return pd.DataFrame(rows)


def test_eda_summary_regenerates_duration_coverage_and_timing(tmp_path):
    destination = tmp_path / "eda_summary.json"
    summary = create_eda_summary(sample(), destination)
    written = json.loads(destination.read_text(encoding="utf-8"))

    assert written == summary
    assert summary["flood_rows"] == 4
    assert summary["flood_event_duration"] == {
        "events": 3,
        "min_days": 1,
        "median_days": 1.0,
        "max_days": 2,
        "mean_days": pytest.approx(4 / 3),
    }
    coverage = summary["township_coverage"]
    assert coverage["townships"] == 3
    assert coverage["townships_with_flood"] == 2
    assert coverage["flood_rows_by_township"]["a"]["flood_rows"] == 3
    assert coverage["flood_rows_by_township"]["c"]["flood_rows"] == 0
    assert summary["positive_day_assessment"]["flood_rows"] == 4
    assert summary["positive_day_assessment"]["test_block_flood_rows"] == 1
    assert summary["positive_day_assessment"]["test_block_start"] == "2024-01-05"
    assert "same calendar day" in summary["feature_target_timing"]
    assert "not a forecast lead" in summary["feature_target_timing"]


def test_bago_positive_days_match_chronological_test_block(tmp_path):
    if not RAW_DATA.exists():
        pytest.skip("source dataset is not present")
    data = load_raw(RAW_DATA)
    validate_daily_data(data)
    summary = create_eda_summary(data, tmp_path / "eda_summary.json")

    assert summary["flood_rows"] == 220
    assert summary["positive_day_assessment"]["flood_rows"] == 220
    assert summary["positive_day_assessment"]["test_block_flood_rows"] == 11
    assert summary["labels_by_year"]["2025"]["flood_rows"] == 11
