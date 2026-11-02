from __future__ import annotations

import json

import joblib
import pandas as pd

from .config import MODEL_FEATURES, MODEL_METADATA_PATH, MODEL_PATH


def predict_feature_rows(
    data: pd.DataFrame,
    model_path=None,
    metadata_path=None,
) -> pd.DataFrame:
    """Score already engineered rows; this function never reads labels or impact fields."""
    model_path = MODEL_PATH if model_path is None else model_path
    metadata_path = MODEL_METADATA_PATH if metadata_path is None else metadata_path
    missing = sorted(set(MODEL_FEATURES) - set(data.columns))
    if missing:
        raise ValueError(f"Missing model features: {missing}")
    pipeline = joblib.load(model_path)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    threshold = float(metadata["threshold"])
    probability = pipeline.predict_proba(data.loc[:, list(MODEL_FEATURES)])[:, 1]
    output_columns = [column for column in ("date", "township_id") if column in data]
    output = data.loc[:, output_columns].copy()
    output["flood_probability"] = probability
    output["predicted_flood"] = (probability >= threshold).astype(int)
    output["threshold"] = threshold
    return output
