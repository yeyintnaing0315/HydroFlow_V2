import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

ML_ROOT = Path(__file__).resolve().parents[2] / "ml"
sys.path.insert(0, str(ML_ROOT))

from app.services.live_features import features_on_or_after
from hydroflow_ml.config import MODEL_FEATURES
from hydroflow_ml.features import engineer_features


def test_live_feature_rows_match_training_features():
    observations = [
        (date(2024, 1, day), float(day), float(10 + day))
        for day in range(1, 9)
    ]
    live_rows = features_on_or_after(observations, date(2024, 1, 1), "a", 17.0, 96.0)
    source = pd.DataFrame(
        {
            "date": [day for day, _, _ in observations],
            "rainfall_mm": [rain for _, rain, _ in observations],
            "river_discharge_m3s": [discharge for _, _, discharge in observations],
            "township_id": "a",
            "township": "A",
            "lat": 17.0,
            "lng": 96.0,
            "households": None,
            "affected_people": None,
            "flood": 0,
        }
    )
    trained = engineer_features(source).sort_values("date").reset_index(drop=True)

    assert len(live_rows) == len(trained)
    for live, (_, row) in zip(live_rows, trained.iterrows()):
        assert set(MODEL_FEATURES) <= set(live)
        for column in MODEL_FEATURES:
            expected = row[column]
            if isinstance(expected, str):
                assert live[column] == expected
            else:
                assert live[column] == pytest.approx(float(expected))
