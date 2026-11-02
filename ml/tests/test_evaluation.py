import json

import pandas as pd
import pytest
from sklearn.pipeline import Pipeline

from hydroflow_ml.cli import main
from hydroflow_ml.config import FEATURE_DATA, MODEL_METADATA_PATH, MODEL_PATH
from hydroflow_ml.evaluation import (
    evaluate,
    event_level_behavior,
    threshold_behavior,
    township_behavior,
)
from hydroflow_ml.model import train
from hydroflow_ml.splits import chronological_split


def _paths(tmp_path):
    return {
        "model_path": tmp_path / "model.joblib",
        "metadata_path": tmp_path / "metadata.json",
        "split_path": tmp_path / "splits.csv",
        "metrics_path": tmp_path / "metrics.json",
        "predictions_path": tmp_path / "predictions.csv",
    }


def test_threshold_township_and_event_reports_respect_sample_size():
    labels = pd.Series([0, 1, 1, 0, 1])
    probability = pd.Series([0.1, 0.2, 0.8, 0.95, 0.99])
    behavior = threshold_behavior(labels, probability, 0.8)
    selected = [row for row in behavior if row["selected_on_validation"]]
    assert len(selected) == 1
    assert selected[0]["threshold"] == 0.8
    assert selected[0]["recall"] == pytest.approx(2 / 3)

    scored = pd.DataFrame(
        {
            "date": ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-01"],
            "township_id": ["sparse", "sparse", "sparse", "sparse", "enough"],
            "actual_flood": [1, 0, 0, 0, 1],
            "predicted_flood": [0, 0, 0, 0, 1],
        }
    )
    enough = pd.concat(
        [
            scored,
            pd.DataFrame(
                {
                    "date": [f"2024-02-0{day}" for day in range(1, 5)],
                    "township_id": ["enough"] * 4,
                    "actual_flood": [1, 1, 1, 1],
                    "predicted_flood": [1, 0, 1, 0],
                }
            ),
        ],
        ignore_index=True,
    )
    townships = township_behavior(enough)
    by_id = {row["township_id"]: row for row in townships["by_township"]}
    assert by_id["sparse"]["status"] == "insufficient_positive_sample"
    assert "precision" not in by_id["sparse"]
    assert by_id["enough"]["status"] == "reported"
    assert by_id["enough"]["flood_rows"] == 5
    assert by_id["enough"]["recall"] == pytest.approx(3 / 5)

    events = event_level_behavior(
        pd.DataFrame(
            {
                "date": ["2024-03-01", "2024-03-02", "2024-03-04"],
                "township_id": ["a", "a", "a"],
                "actual_flood": [1, 1, 1],
                "predicted_flood": [0, 1, 0],
            }
        )
    )
    assert events["events"] == 2
    assert events["detected_events"] == 1
    assert events["event_recall"] == pytest.approx(0.5)
    assert events["status"] == "limited_sample"


def test_evaluation_is_repeatable_and_does_not_retrain(tmp_path, monkeypatch, feature_frame):
    paths = _paths(tmp_path)
    train(
        feature_frame,
        model_path=paths["model_path"],
        metadata_path=paths["metadata_path"],
        split_path=paths["split_path"],
    )
    model_bytes = paths["model_path"].read_bytes()
    metadata_text = paths["metadata_path"].read_text(encoding="utf-8")

    def fail_fit(*args, **kwargs):
        raise AssertionError("evaluation must not fit or retrain the pipeline")

    monkeypatch.setattr(Pipeline, "fit", fail_fit)
    first = evaluate(feature_frame, **{key: paths[key] for key in (
        "model_path", "metadata_path", "metrics_path", "predictions_path"
    )})
    second = evaluate(feature_frame, **{key: paths[key] for key in (
        "model_path", "metadata_path", "metrics_path", "predictions_path"
    )})

    assert first == second
    assert paths["model_path"].read_bytes() == model_bytes
    assert paths["metadata_path"].read_text(encoding="utf-8") == metadata_text
    assert first["retrained_during_evaluation"] is False
    assert first["test_data_was_used_for_training_or_threshold_selection"] is False
    assert "threshold_behavior" in first["test"]
    assert "township_behavior" in first["test"]
    assert "event_behavior" in first["test"]
    assert first["baseline_comparison"]["naive_always_negative"]["recall"] == 0
    assert first["baseline_comparison"]["naive_always_positive"]["recall"] == 1
    assert first["baseline_comparison"]["published_hydroflow_random_forest"]["flood_f1"] == 0.01
    assert first["test"]["accuracy_role"].startswith("secondary")

    changed = feature_frame.copy()
    split = chronological_split(feature_frame)
    changed.loc[split == "test", "flood"] = 1 - changed.loc[split == "test", "flood"]
    updated = evaluate(changed, **{key: paths[key] for key in (
        "model_path", "metadata_path", "metrics_path", "predictions_path"
    )})
    assert updated["validation"]["f1"] == first["validation"]["f1"]
    assert updated["validation"]["recall"] == first["validation"]["recall"]
    assert updated["test"]["flood_rows"] != first["test"]["flood_rows"]
    assert paths["model_path"].read_bytes() == model_bytes
    assert json.loads(metadata_text)["threshold"] == updated["test"]["threshold"]


def test_evaluate_command_leaves_the_saved_model_untouched(tmp_path, monkeypatch, capsys, feature_frame):
    features = tmp_path / "features.csv"
    feature_frame.to_csv(features, index=False)
    paths = _paths(tmp_path)
    monkeypatch.setattr("hydroflow_ml.cli.FEATURE_DATA", features)
    monkeypatch.setattr("hydroflow_ml.model.MODEL_PATH", paths["model_path"])
    monkeypatch.setattr("hydroflow_ml.model.MODEL_METADATA_PATH", paths["metadata_path"])
    monkeypatch.setattr("hydroflow_ml.model.SPLIT_DATA", paths["split_path"])
    monkeypatch.setattr("hydroflow_ml.evaluation.MODEL_PATH", paths["model_path"])
    monkeypatch.setattr("hydroflow_ml.evaluation.MODEL_METADATA_PATH", paths["metadata_path"])
    monkeypatch.setattr("hydroflow_ml.evaluation.METRICS_PATH", paths["metrics_path"])
    monkeypatch.setattr(
        "hydroflow_ml.evaluation.ARTIFACT_DIR",
        tmp_path,
    )

    assert main(["train"]) == 0
    model_bytes = paths["model_path"].read_bytes()
    assert main(["evaluate"]) == 0
    metrics = json.loads(paths["metrics_path"].read_text(encoding="utf-8"))
    assert metrics["test_data_was_used_for_training_or_threshold_selection"] is False
    assert "baseline_comparison" in metrics
    assert paths["model_path"].read_bytes() == model_bytes
    capsys.readouterr()


def test_saved_bago_evaluation_matches_untouched_test_block(tmp_path):
    if not MODEL_PATH.exists() or not FEATURE_DATA.exists() or not MODEL_METADATA_PATH.exists():
        pytest.skip("saved model or feature table is not present")
    data = pd.read_csv(FEATURE_DATA, parse_dates=["date"])
    before = MODEL_PATH.read_bytes()
    metadata_before = MODEL_METADATA_PATH.read_text(encoding="utf-8")
    metrics = evaluate(
        data,
        metrics_path=tmp_path / "metrics.json",
        predictions_path=tmp_path / "predictions.csv",
    )
    assert MODEL_PATH.read_bytes() == before
    assert MODEL_METADATA_PATH.read_text(encoding="utf-8") == metadata_before
    assert metrics["test"]["flood_rows"] == 11
    assert metrics["test"]["rows"] == 8052
    assert "accuracy" not in metrics["test"]
    assert "accuracy_secondary" in metrics["test"]
    comparison = metrics["baseline_comparison"]
    assert comparison["naive_always_negative"]["f1"] == 0
    assert comparison["naive_always_negative"]["accuracy_secondary"] > metrics["test"]["f1"]
    assert comparison["published_hydroflow_random_forest"]["test_flood_days"] == 11
