from __future__ import annotations

import json

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from .config import (
    CATEGORICAL_FEATURES,
    MODEL_FEATURES,
    MODEL_METADATA_PATH,
    MODEL_PATH,
    NUMERIC_FEATURES,
    RANDOM_STATE,
    SPLIT_DATA,
    TARGET,
)
from .splits import assert_temporal_order, chronological_split

MODEL_VERSION = "baseline-logistic-v2"


def make_pipeline() -> Pipeline:
    numeric = Pipeline(
        [
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
        ]
    )
    transformers = [("numeric", numeric, list(NUMERIC_FEATURES))]
    if CATEGORICAL_FEATURES:
        categorical = Pipeline(
            [
                ("impute", SimpleImputer(strategy="most_frequent")),
                ("one_hot", OneHotEncoder(handle_unknown="ignore")),
            ]
        )
        transformers.append(("categorical", categorical, list(CATEGORICAL_FEATURES)))
    preprocessing = ColumnTransformer(transformers)
    return Pipeline(
        [
            ("preprocess", preprocessing),
            (
                "classifier",
                LogisticRegression(
                    class_weight="balanced",
                    max_iter=2000,
                    random_state=RANDOM_STATE,
                    solver="liblinear",
                ),
            ),
        ]
    )


def select_threshold(y_true: pd.Series, probabilities: np.ndarray) -> tuple[float, float]:
    """Select the validation threshold that maximizes flood-class F1."""
    best_threshold, best_f1 = 0.5, -1.0
    for threshold in np.linspace(0.01, 0.99, 99):
        predicted = probabilities >= threshold
        tp = int(((y_true == 1) & predicted).sum())
        fp = int(((y_true == 0) & predicted).sum())
        fn = int(((y_true == 1) & ~predicted).sum())
        denominator = 2 * tp + fp + fn
        f1 = 0.0 if denominator == 0 else 2 * tp / denominator
        if f1 > best_f1:
            best_threshold, best_f1 = float(threshold), float(f1)
    return best_threshold, best_f1


def train(
    data: pd.DataFrame,
    model_path=None,
    metadata_path=None,
    split_path=None,
) -> tuple[Pipeline, dict, pd.Series]:
    model_path = MODEL_PATH if model_path is None else model_path
    metadata_path = MODEL_METADATA_PATH if metadata_path is None else metadata_path
    split_path = SPLIT_DATA if split_path is None else split_path
    split = chronological_split(data)
    assert_temporal_order(data, split)
    pipeline = make_pipeline()
    train_mask = split == "train"
    validation_mask = split == "validation"
    pipeline.fit(data.loc[train_mask, list(MODEL_FEATURES)], data.loc[train_mask, TARGET])

    validation_probability = pipeline.predict_proba(
        data.loc[validation_mask, list(MODEL_FEATURES)]
    )[:, 1]
    threshold, validation_f1 = select_threshold(
        data.loc[validation_mask, TARGET], validation_probability
    )

    preprocess = pipeline.named_steps["preprocess"]
    feature_names = preprocess.get_feature_names_out()
    coefficients = pipeline.named_steps["classifier"].coef_[0]
    coefficient_rows = sorted(
        (
            {"feature": str(name), "coefficient": float(value)}
            for name, value in zip(feature_names, coefficients)
        ),
        key=lambda row: abs(row["coefficient"]),
        reverse=True,
    )
    fitted_rows = int(
        pipeline.named_steps["preprocess"]
        .named_transformers_["numeric"]
        .named_steps["scale"]
        .n_samples_seen_
    )
    split_summary = {
        name: {
            "rows": int((split == name).sum()),
            "flood_rows": int(data.loc[split == name, TARGET].sum()),
            "start": pd.to_datetime(data.loc[split == name, "date"]).min().date().isoformat(),
            "end": pd.to_datetime(data.loc[split == name, "date"]).max().date().isoformat(),
        }
        for name in ("train", "validation", "test")
    }
    if fitted_rows != split_summary["train"]["rows"]:
        raise RuntimeError("Classifier saw a different row count than the train block")
    metadata = {
        "version": MODEL_VERSION,
        "model": "class-weighted LogisticRegression",
        "class_weight": "balanced",
        "random_state": RANDOM_STATE,
        "model_features": list(MODEL_FEATURES),
        "explicitly_excluded_leakage_fields": ["households", "affected_people"],
        "fitted_rows": fitted_rows,
        "test_rows_excluded_from_fit": split_summary["test"]["rows"],
        "threshold": threshold,
        "threshold_selection": "Maximum F1 on chronological validation block only",
        "validation_f1_at_selected_threshold": validation_f1,
        "calibration": (
            "Not applied: the single chronological validation block is used for threshold "
            "selection; using it again for calibration would not provide independent evidence."
        ),
        "tree_baseline": {
            "included": False,
            "reason": (
                "EDA does not justify fitting a second model. The chronological train block has "
                f"{split_summary['train']['flood_rows']} flood days and the untouched test block has "
                f"{split_summary['test']['flood_rows']}. The persisted baseline stays an interpretable "
                "class-weighted logistic regression. Evaluation compares it with naive label rules and "
                "the published Hydroflow RandomForest metrics instead of training a new tree."
            ),
        },
        "split": split_summary,
        "coefficients": coefficient_rows,
    }
    model_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, model_path)
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    split_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        {
            "date": pd.to_datetime(data["date"]).dt.strftime("%Y-%m-%d"),
            "township_id": data["township_id"],
            "split": split,
        }
    ).to_csv(split_path, index=False)
    return pipeline, metadata, split
