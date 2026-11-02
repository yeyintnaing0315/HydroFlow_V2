import json

import pandas as pd

from hydroflow_ml.cli import main
from hydroflow_ml.config import MODEL_FEATURES
from hydroflow_ml.help_model import evaluate_help, predict_help_rows, train_help
from hydroflow_ml.splits import chronological_split


def _with_impacts(frame: pd.DataFrame) -> pd.DataFrame:
    scored = frame.copy()
    scored["households"] = scored["flood"] * 20
    scored["affected_people"] = scored["flood"] * 80
    return scored


def test_train_help_excludes_impacts_and_scores_without_them(tmp_path, feature_frame):
    frame = _with_impacts(feature_frame)
    model_path = tmp_path / "help.joblib"
    metadata_path = tmp_path / "help.json"
    bundle, metadata, split = train_help(frame, model_path=model_path, metadata_path=metadata_path)

    train_rows = int((split == "train").sum())
    help_rows = int(((split == "train") & (frame["flood"] == 1)).sum())
    assert metadata["version"] == "flood-help-v2"
    assert metadata["fitted_classifier_rows"] == train_rows
    assert metadata["fitted_magnitude_rows"] == help_rows
    assert metadata["explicitly_excluded_leakage_fields"] == ["households", "affected_people", "flood"]
    assert set(metadata["model_features"]) == set(MODEL_FEATURES)
    assert metadata["test_rows_excluded_from_fit"] == int((split == "test").sum())
    seen = bundle["classifier"].named_steps["preprocess"].named_transformers_["numeric"].named_steps["scale"]
    assert int(seen.n_samples_seen_) == train_rows
    magnitude_seen = (
        bundle["people_regressor"].named_steps["preprocess"].named_transformers_["numeric"].named_steps["scale"]
    )
    assert int(magnitude_seen.n_samples_seen_) == help_rows

    sample = frame.loc[split == "test", ["date", "township_id", *MODEL_FEATURES]].head(3)
    predictions = predict_help_rows(sample, model_path=model_path, metadata_path=metadata_path)
    assert len(predictions) == 3
    assert predictions["help_probability"].between(0, 1).all()
    assert set(predictions["predicted_help"]).issubset({0, 1})
    assert (predictions["expected_affected_people"] >= 0).all()
    assert (predictions["expected_households"] >= 0).all()
    assert (predictions["drinking_water_liters_3d"] == predictions["expected_affected_people"] * 45).all()
    assert "households" not in predictions.columns
    assert "affected_people" not in predictions.columns
    assert "flood" not in predictions.columns


def test_evaluate_help_does_not_refit(tmp_path, feature_frame):
    frame = _with_impacts(feature_frame)
    model_path = tmp_path / "help.joblib"
    metadata_path = tmp_path / "help.json"
    metrics_path = tmp_path / "metrics.json"
    predictions_path = tmp_path / "predictions.csv"
    train_help(frame, model_path=model_path, metadata_path=metadata_path)
    before = model_path.read_bytes()
    metrics = evaluate_help(
        frame,
        model_path=model_path,
        metadata_path=metadata_path,
        metrics_path=metrics_path,
        predictions_path=predictions_path,
    )
    assert model_path.read_bytes() == before
    assert metrics["retrained_during_evaluation"] is False
    assert metrics["test_data_was_used_for_training_or_threshold_selection"] is False
    assert "f1" in metrics["test"]
    saved = json.loads(metrics_path.read_text(encoding="utf-8"))
    assert saved["test"]["help_rows"] == int(
        ((chronological_split(frame) == "test") & (frame["flood"] == 1)).sum()
    )


def test_train_help_command(tmp_path, monkeypatch, feature_frame):
    frame = _with_impacts(feature_frame)
    features = tmp_path / "features.csv"
    frame.to_csv(features, index=False)
    model_path = tmp_path / "help.joblib"
    metadata_path = tmp_path / "help.json"
    prediction_path = tmp_path / "predictions.csv"
    monkeypatch.setattr("hydroflow_ml.cli.FEATURE_DATA", features)
    monkeypatch.setattr("hydroflow_ml.help_model.HELP_MODEL_PATH", model_path)
    monkeypatch.setattr("hydroflow_ml.help_model.HELP_METADATA_PATH", metadata_path)

    assert main(["train-help"]) == 0
    sample = frame.loc[:, ["date", *MODEL_FEATURES]].head(2)
    sample_path = tmp_path / "sample.csv"
    sample.to_csv(sample_path, index=False)
    assert main(["predict-help", str(sample_path), "--output", str(prediction_path)]) == 0
    predictions = pd.read_csv(prediction_path)
    assert list(predictions["assistance_priority"])
    assert "affected_people" not in predictions.columns
