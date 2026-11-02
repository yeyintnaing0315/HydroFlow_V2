import os
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

from app.services.live_features import NEW_MODEL_FEATURES, row_has_model_features


class ModelUnavailableError(RuntimeError):
    pass


def model_path() -> Path:
    default = Path(__file__).resolve().parents[3] / "ml" / "models" / "bago_flood_model.joblib"
    return Path(os.getenv("MODEL_PATH", default))


def metadata_path() -> Path:
    default = Path(__file__).resolve().parents[3] / "ml" / "models" / "bago_flood_model_metadata.json"
    return Path(os.getenv("MODEL_METADATA_PATH", default))


def feature_names(metadata: dict[str, Any] | None = None) -> list[str]:
    payload = metadata if metadata is not None else load_model()[1]
    listed = payload.get("features") or payload.get("model_features")
    if listed:
        return [str(name) for name in listed]
    if payload.get("selected_model") or payload.get("version"):
        return list(NEW_MODEL_FEATURES)
    return []


def decision_threshold(metadata: dict[str, Any]) -> float:
    return float(metadata.get("decision_threshold", metadata.get("threshold", 0.5)))


def model_version_name(metadata: dict[str, Any]) -> str:
    return str(metadata.get("selected_model") or metadata.get("version") or "baseline-logistic-v2")


@lru_cache(maxsize=1)
def load_model() -> tuple[Any, dict[str, Any]]:
    path = model_path()
    metadata = metadata_path()
    if not path.is_file() or not metadata.is_file():
        raise ModelUnavailableError("Persisted model artifact or metadata not found")
    try:
        model = joblib.load(path)
        model_metadata = json.loads(metadata.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ModelUnavailableError("Persisted model artifact could not be loaded") from exc
    if not callable(getattr(model, "predict_proba", None)):
        raise ModelUnavailableError("Persisted artifact does not expose predict_proba()")
    return model, model_metadata


def predict(features: dict[str, float | str]) -> tuple[float, int, float, str]:
    model, metadata = load_model()
    names = feature_names(metadata)
    if names and not row_has_model_features(features, names):
        raise ValueError("Model rejected prediction features")
    try:
        frame = pd.DataFrame([{name: features[name] for name in names}]) if names else pd.DataFrame([features])
        probability = float(model.predict_proba(frame)[:, 1][0])
        threshold = decision_threshold(metadata)
    except Exception as exc:
        raise ValueError("Model rejected prediction features") from exc
    return (
        probability,
        int(probability >= threshold),
        threshold,
        model_version_name(metadata),
    )


def predict_with_backup(
    features: dict[str, float | str],
) -> tuple[float, int, float, str, float | None]:
    """Score with the served gradient-boosting model; logistic backup only if primary fails."""
    from app.services.prediction_secondary import predict_secondary

    try:
        probability, predicted, threshold, version = predict(features)
    except ValueError:
        backup = predict_secondary(features)
        if backup is None:
            raise
        return backup[0], backup[1], backup[2], f"backup:{backup[3]}", None
    backup = predict_secondary(features)
    secondary_probability = float(backup[0]) if backup is not None else None
    return probability, predicted, threshold, version, secondary_probability


def predict_probabilities(rows: list[dict[str, Any] | None]) -> list[float | None]:
    """Score many prepared rows in one model call. Missing features stay None."""
    model, metadata = load_model()
    names = feature_names(metadata)
    usable: list[dict[str, Any]] = []
    positions: list[int] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        if names and not row_has_model_features(row, names):
            continue
        usable.append({name: row[name] for name in names} if names else dict(row))
        positions.append(index)
    found: list[float | None] = [None] * len(rows)
    if not usable:
        return found
    try:
        frame = pd.DataFrame(usable)
        probabilities = model.predict_proba(frame)[:, 1]
    except Exception:
        return found
    for position, probability in zip(positions, probabilities, strict=True):
        found[position] = float(probability)
    return found
