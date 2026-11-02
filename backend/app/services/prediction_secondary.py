import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

from app.services.live_features import row_has_model_features
from app.services.prediction import ModelUnavailableError, decision_threshold, model_version_name


def model_path() -> Path:
    default = (
        Path(__file__).resolve().parents[3] / "ml" / "models" / "bago_flood_model_logistic.joblib"
    )
    return Path(os.getenv("SECONDARY_MODEL_PATH", default))


def metadata_path() -> Path:
    default = (
        Path(__file__).resolve().parents[3]
        / "ml"
        / "models"
        / "bago_flood_model_logistic_metadata.json"
    )
    return Path(os.getenv("SECONDARY_MODEL_METADATA_PATH", default))


@lru_cache(maxsize=1)
def load_secondary_model() -> tuple[Any, dict[str, Any]]:
    path = model_path()
    metadata_file = metadata_path()
    if not path.is_file() or not metadata_file.is_file():
        raise ModelUnavailableError("Secondary flood model artifact or metadata not found")
    try:
        model = joblib.load(path)
        metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ModelUnavailableError("Secondary flood model artifact could not be loaded") from exc
    if not callable(getattr(model, "predict_proba", None)):
        raise ModelUnavailableError("Secondary artifact does not expose predict_proba()")
    return model, metadata


def feature_names(metadata: dict[str, Any] | None = None) -> list[str]:
    payload = metadata if metadata is not None else load_secondary_model()[1]
    listed = payload.get("features") or payload.get("model_features")
    if listed:
        return [str(name) for name in listed]
    return []


def predict_secondary(features: dict[str, float | str]) -> tuple[float, int, float, str] | None:
    try:
        model, metadata = load_secondary_model()
    except ModelUnavailableError:
        return None
    names = feature_names(metadata)
    if names and not row_has_model_features(features, names):
        return None
    try:
        frame = pd.DataFrame([{name: features[name] for name in names}]) if names else pd.DataFrame([features])
        probability = float(model.predict_proba(frame)[:, 1][0])
        threshold = decision_threshold(metadata)
    except Exception:
        return None
    return (
        probability,
        int(probability >= threshold),
        threshold,
        model_version_name(metadata),
    )
