from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DATA = PROJECT_ROOT / "data" / "raw" / "bago_daily.csv"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
ARTIFACT_DIR = PROJECT_ROOT / "artifacts"

CANONICAL_DATA = PROCESSED_DIR / "validated_daily.csv"
FEATURE_DATA = PROCESSED_DIR / "model_features.csv"
SPLIT_DATA = PROCESSED_DIR / "split_assignments.csv"

MODEL_PATH = ARTIFACT_DIR / "flood_logistic_pipeline.joblib"
MODEL_METADATA_PATH = ARTIFACT_DIR / "model_metadata.json"
METRICS_PATH = ARTIFACT_DIR / "evaluation_metrics.json"
EDA_PATH = ARTIFACT_DIR / "eda_summary.json"
HELP_MODEL_PATH = ARTIFACT_DIR / "flood_help_pipeline.joblib"
HELP_METADATA_PATH = ARTIFACT_DIR / "help_model_metadata.json"
HELP_METRICS_PATH = ARTIFACT_DIR / "help_evaluation_metrics.json"
HELP_PREDICTIONS_PATH = ARTIFACT_DIR / "help_evaluation_predictions.csv"
ALLOCATION_MODEL_PATH = ARTIFACT_DIR / "allocation_pipeline.joblib"
ALLOCATION_METADATA_PATH = ARTIFACT_DIR / "allocation_model_metadata.json"
TOPREDICT_EDA_PATH = ARTIFACT_DIR / "topredict_eda_summary.json"

RANDOM_STATE = 42
TARGET = "flood"
IMPACT_COLUMNS = ("households", "affected_people")

NUMERIC_FEATURES = (
    "rainfall_mm",
    "river_discharge_m3s",
    "rainfall_3d_mm",
    "rainfall_7d_mm",
    "rainfall_lag_1d_mm",
    "discharge_lag_1d_m3s",
    "discharge_delta_1d_m3s",
    "discharge_3d_mean_m3s",
    "day_of_year_sin",
    "day_of_year_cos",
    "lat",
    "lng",
)
CATEGORICAL_FEATURES = ()
MODEL_FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES
