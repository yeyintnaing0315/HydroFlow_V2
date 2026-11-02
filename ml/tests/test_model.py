import json

import pandas as pd

from hydroflow_ml.cli import main
from hydroflow_ml.config import MODEL_FEATURES
from hydroflow_ml.inference import predict_feature_rows
from hydroflow_ml.model import train
from hydroflow_ml.splits import chronological_split


def test_train_command_saves_pipeline_metadata_and_offline_inference(
    tmp_path, monkeypatch, capsys, feature_frame
):
    frame = feature_frame
    features = tmp_path / "features.csv"
    frame.to_csv(features, index=False)
    model_path = tmp_path / "model.joblib"
    metadata_path = tmp_path / "metadata.json"
    split_path = tmp_path / "splits.csv"
    prediction_path = tmp_path / "predictions.csv"
    monkeypatch.setattr("hydroflow_ml.cli.FEATURE_DATA", features)
    monkeypatch.setattr("hydroflow_ml.model.MODEL_PATH", model_path)
    monkeypatch.setattr("hydroflow_ml.model.MODEL_METADATA_PATH", metadata_path)
    monkeypatch.setattr("hydroflow_ml.model.SPLIT_DATA", split_path)
    monkeypatch.setattr("hydroflow_ml.inference.MODEL_PATH", model_path)
    monkeypatch.setattr("hydroflow_ml.inference.MODEL_METADATA_PATH", metadata_path)

    assert main(["train"]) == 0
    assert model_path.exists()
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    split = chronological_split(frame)
    train_rows = int((split == "train").sum())
    test_rows = int((split == "test").sum())

    assert metadata["model"] == "class-weighted LogisticRegression"
    assert metadata["version"] == "baseline-logistic-v2"
    assert metadata["class_weight"] == "balanced"
    assert metadata["fitted_rows"] == train_rows
    assert metadata["test_rows_excluded_from_fit"] == test_rows
    assert metadata["tree_baseline"]["included"] is False
    assert set(metadata["model_features"]) == set(MODEL_FEATURES)
    assert metadata["explicitly_excluded_leakage_fields"] == ["households", "affected_people"]
    assert metadata["split"]["train"]["end"] < metadata["split"]["validation"]["start"]
    assert metadata["split"]["validation"]["end"] < metadata["split"]["test"]["start"]
    assert metadata["coefficients"]

    sample = frame.loc[split == "test", ["date", *MODEL_FEATURES]].head(2)
    sample_path = tmp_path / "sample.csv"
    sample.to_csv(sample_path, index=False)
    assert main(["predict", str(sample_path), "--output", str(prediction_path)]) == 0
    predictions = pd.read_csv(prediction_path)
    assert len(predictions) == 2
    assert predictions["flood_probability"].between(0, 1).all()
    assert set(predictions["predicted_flood"]).issubset({0, 1})
    assert "flood" not in predictions.columns
    assert "households" not in predictions.columns
    capsys.readouterr()


def test_training_uses_only_the_train_block(tmp_path, feature_frame):
    frame = feature_frame
    pipeline, metadata, split = train(
        frame,
        model_path=tmp_path / "model.joblib",
        metadata_path=tmp_path / "metadata.json",
        split_path=tmp_path / "splits.csv",
    )
    seen = pipeline.named_steps["preprocess"].named_transformers_["numeric"].named_steps["scale"]
    assert int(seen.n_samples_seen_) == int((split == "train").sum())
    scored = predict_feature_rows(
        frame.loc[split == "test", ["date", *MODEL_FEATURES]],
        model_path=tmp_path / "model.joblib",
        metadata_path=tmp_path / "metadata.json",
    )
    assert len(scored) == int((split == "test").sum())
    assert metadata["tree_baseline"]["included"] is False
