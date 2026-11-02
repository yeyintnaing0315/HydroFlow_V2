from __future__ import annotations

import json

import joblib
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

from .config import (
    ARTIFACT_DIR,
    METRICS_PATH,
    MODEL_FEATURES,
    MODEL_METADATA_PATH,
    MODEL_PATH,
    TARGET,
)
from .splits import chronological_split

MIN_TOWNSHIP_FLOOD_ROWS = 5
MIN_EVENTS_FOR_RATE = 5
THRESHOLD_GRID = (0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.97, 0.99)

# Published earlier-project test metrics. That run used a class-weighted
# RandomForest, a different feature set, and a test window starting 2025-04-01.
PUBLISHED_HYDROFLOW_BASELINE = {
    "source": "Hydroflow/artifacts/metrics.json",
    "model": "class-weighted RandomForest",
    "test_start": "2025-04-01",
    "test_rows": 8030,
    "test_flood_days": 11,
    "flood_precision": 0.005,
    "flood_recall": 0.818,
    "flood_f1": 0.01,
    "accuracy": 0.772,
    "comparison_note": (
        "These are the published earlier-project figures. That test window starts one day "
        "later than this chronological test block and uses a different feature set, so the "
        "comparison is context for the same sparse test year rather than a paired rescore."
    ),
}


def _operating_thresholds(operating_threshold: float) -> list[float]:
    values: list[float] = []
    for value in (*THRESHOLD_GRID, float(operating_threshold)):
        if not any(abs(value - seen) < 1e-9 for seen in values):
            values.append(float(value))
    return sorted(values)


def _binary_counts(y_true: pd.Series, predicted) -> dict[str, float | int]:
    labels = y_true.astype(int)
    decisions = pd.Series(predicted, index=labels.index).astype(int)
    return {
        "precision": float(precision_score(labels, decisions, zero_division=0)),
        "recall": float(recall_score(labels, decisions, zero_division=0)),
        "f1": float(f1_score(labels, decisions, zero_division=0)),
        "accuracy_secondary": float(accuracy_score(labels, decisions)),
        "predicted_positive_rows": int(decisions.sum()),
    }


def classification_metrics(
    y_true: pd.Series, probability, threshold: float
) -> tuple[dict, object]:
    predicted = (probability >= threshold).astype(int)
    matrix = confusion_matrix(y_true, predicted, labels=[0, 1])
    metrics = {
        "threshold": float(threshold),
        **_binary_counts(y_true, predicted),
        "pr_auc_average_precision": float(average_precision_score(y_true, probability)),
        "roc_auc": float(roc_auc_score(y_true, probability)),
        "confusion_matrix": {
            "labels": [0, 1],
            "values": matrix.tolist(),
            "tn": int(matrix[0, 0]),
            "fp": int(matrix[0, 1]),
            "fn": int(matrix[1, 0]),
            "tp": int(matrix[1, 1]),
        },
        "rows": int(len(y_true)),
        "flood_rows": int(y_true.sum()),
        "accuracy_role": "secondary because flood days are about 0.55% of rows",
    }
    return metrics, predicted


def threshold_behavior(y_true: pd.Series, probability, operating_threshold: float) -> list[dict]:
    """Describe precision, recall, and F1 across thresholds. Selection stays on validation."""
    rows = []
    for threshold in _operating_thresholds(operating_threshold):
        predicted = probability >= threshold
        rows.append(
            {
                "threshold": threshold,
                "selected_on_validation": abs(threshold - operating_threshold) < 1e-9,
                **_binary_counts(y_true, predicted),
            }
        )
    return rows


def township_behavior(frame: pd.DataFrame) -> dict:
    """Report per-township rates only where the block has enough flood days."""
    by_township = []
    reported = 0
    for township, group in frame.groupby("township_id", sort=True):
        flood_rows = int(group["actual_flood"].sum())
        entry = {
            "township_id": str(township),
            "rows": int(len(group)),
            "flood_rows": flood_rows,
            "predicted_positive_rows": int(group["predicted_flood"].sum()),
        }
        if flood_rows >= MIN_TOWNSHIP_FLOOD_ROWS:
            entry["status"] = "reported"
            entry.update(_binary_counts(group["actual_flood"], group["predicted_flood"]))
            reported += 1
        else:
            entry["status"] = "insufficient_positive_sample"
        by_township.append(entry)
    return {
        "minimum_flood_rows": MIN_TOWNSHIP_FLOOD_ROWS,
        "townships": len(by_township),
        "townships_with_reported_metrics": reported,
        "by_township": by_township,
    }


def event_level_behavior(frame: pd.DataFrame) -> dict:
    """Score consecutive township flood runs. A run is detected if any day is predicted."""
    floods = frame.loc[
        frame["actual_flood"].astype(int) == 1, ["township_id", "date", "predicted_flood"]
    ].copy()
    note = (
        "An event is one township's run of consecutive flood days. "
        "It is detected when at least one of those days is predicted positive."
    )
    if floods.empty:
        return {
            "events": 0,
            "detected_events": 0,
            "event_recall": None,
            "status": "no_events",
            "note": note,
        }
    floods["date"] = pd.to_datetime(floods["date"])
    floods = floods.sort_values(["township_id", "date"], kind="stable")
    previous = floods.groupby("township_id", sort=False)["date"].shift(1)
    starts = previous.isna() | (floods["date"] - previous).dt.days.ne(1)
    floods["event_key"] = (
        floods["township_id"].astype(str)
        + "-"
        + starts.groupby(floods["township_id"], sort=False).cumsum().astype(str)
    )
    detected_by_event = floods.groupby("event_key", sort=False)["predicted_flood"].max().astype(int)
    n_events = int(len(detected_by_event))
    detected = int(detected_by_event.sum())
    status = "reported" if n_events >= MIN_EVENTS_FOR_RATE else "limited_sample"
    return {
        "events": n_events,
        "detected_events": detected,
        "event_recall": None if n_events == 0 else detected / n_events,
        "minimum_events_for_interpretation": MIN_EVENTS_FOR_RATE,
        "status": status,
        "note": note,
    }


def baseline_comparison(y_true: pd.Series, current: dict) -> dict:
    labels = y_true.astype(int)
    always_negative = _binary_counts(labels, pd.Series(0, index=labels.index))
    always_positive = _binary_counts(labels, pd.Series(1, index=labels.index))
    return {
        "accuracy_note": (
            "Accuracy is secondary. Flood days are about 0.55% of the source rows, so a rule "
            "that never predicts flooding already has very high accuracy."
        ),
        "current_model_test": {
            "precision": current["precision"],
            "recall": current["recall"],
            "f1": current["f1"],
            "pr_auc_average_precision": current["pr_auc_average_precision"],
            "roc_auc": current["roc_auc"],
            "accuracy_secondary": current["accuracy_secondary"],
        },
        "naive_always_negative": always_negative,
        "naive_always_positive": always_positive,
        "published_hydroflow_random_forest": PUBLISHED_HYDROFLOW_BASELINE,
    }


def evaluate(
    data: pd.DataFrame,
    model_path=None,
    metadata_path=None,
    metrics_path=None,
    predictions_path=None,
) -> dict:
    model_path = MODEL_PATH if model_path is None else model_path
    metadata_path = MODEL_METADATA_PATH if metadata_path is None else metadata_path
    metrics_path = METRICS_PATH if metrics_path is None else metrics_path
    predictions_path = (
        ARTIFACT_DIR / "evaluation_predictions.csv" if predictions_path is None else predictions_path
    )
    pipeline = joblib.load(model_path)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    threshold = float(metadata["threshold"])
    split = chronological_split(data)
    results = {
        "model_path": str(model_path),
        "threshold_source": "chronological validation maximum F1",
        "test_data_was_used_for_training_or_threshold_selection": False,
        "retrained_during_evaluation": False,
    }
    prediction_frames = []
    for block in ("validation", "test"):
        mask = split == block
        block_data = data.loc[mask]
        probability = pipeline.predict_proba(block_data.loc[:, list(MODEL_FEATURES)])[:, 1]
        metrics, predicted = classification_metrics(block_data[TARGET], probability, threshold)
        scored = pd.DataFrame(
            {
                "date": pd.to_datetime(block_data["date"]).dt.strftime("%Y-%m-%d"),
                "township_id": block_data["township_id"].to_numpy(),
                "actual_flood": block_data[TARGET].to_numpy(),
                "flood_probability": probability,
                "predicted_flood": predicted,
                "threshold": threshold,
                "split": block,
            }
        )
        metrics["threshold_behavior"] = threshold_behavior(
            block_data[TARGET], probability, threshold
        )
        metrics["township_behavior"] = township_behavior(scored)
        metrics["event_behavior"] = event_level_behavior(scored)
        results[block] = metrics
        prediction_frames.append(scored)
    results["baseline_comparison"] = baseline_comparison(
        data.loc[split == "test", TARGET], results["test"]
    )
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    predictions_path.parent.mkdir(parents=True, exist_ok=True)
    pd.concat(prediction_frames, ignore_index=True).to_csv(predictions_path, index=False)
    return results
