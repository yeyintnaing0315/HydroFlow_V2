"""Compare the current baseline with NASA POWER soil-wetness features."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, f1_score, precision_score, recall_score, accuracy_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from hydroflow_ml.config import FEATURE_DATA, NUMERIC_FEATURES, CATEGORICAL_FEATURES
from hydroflow_ml.model import select_threshold
from hydroflow_ml.nasa_power import download_township_series
from hydroflow_ml.splits import chronological_split

SOIL_FEATURES = ("soil_wetness_root", "relative_humidity_pct")


def score(data: pd.DataFrame, numeric: tuple[str, ...], categorical: tuple[str, ...]) -> dict:
    split = chronological_split(data)
    transformers = [
        (
            "numeric",
            Pipeline([("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler())]),
            list(numeric),
        )
    ]
    if categorical:
        transformers.append(
            (
                "categorical",
                Pipeline(
                    [
                        ("impute", SimpleImputer(strategy="most_frequent")),
                        ("one_hot", OneHotEncoder(handle_unknown="ignore")),
                    ]
                ),
                list(categorical),
            )
        )
    pipeline = Pipeline(
        [
            ("preprocess", ColumnTransformer(transformers)),
            (
                "classifier",
                LogisticRegression(
                    class_weight="balanced", max_iter=2000, random_state=42, solver="liblinear"
                ),
            ),
        ]
    )
    features = list(numeric) + list(categorical)
    pipeline.fit(data.loc[split == "train", features], data.loc[split == "train", "flood"])
    validation = data.loc[split == "validation"]
    test = data.loc[split == "test"]
    validation_probability = pipeline.predict_proba(validation[features])[:, 1]
    threshold, validation_f1 = select_threshold(validation["flood"], validation_probability)
    probability = pipeline.predict_proba(test[features])[:, 1]
    predicted = probability >= threshold
    return {
        "threshold": threshold,
        "validation_f1": validation_f1,
        "test_precision": float(precision_score(test["flood"], predicted, zero_division=0)),
        "test_recall": float(recall_score(test["flood"], predicted, zero_division=0)),
        "test_f1": float(f1_score(test["flood"], predicted, zero_division=0)),
        "test_pr_auc": float(average_precision_score(test["flood"], probability)),
        "test_accuracy": float(accuracy_score(test["flood"], predicted)),
        "test_predicted_floods": int(np.sum(predicted)),
    }


def main() -> None:
    features = pd.read_csv(FEATURE_DATA, parse_dates=["date"])
    locations = features.groupby("township_id", as_index=False)[["lat", "lng"]].first()
    start = features["date"].min().strftime("%Y%m%d")
    end = features["date"].max().strftime("%Y%m%d")
    nasa = download_township_series(locations, start, end)
    merged = features.merge(nasa, on=["township_id", "date"], how="left")
    coverage = float(merged["soil_wetness_root"].notna().mean())
    results = {
        "nasa_rows": int(len(nasa)),
        "feature_coverage": coverage,
        "baseline": score(merged, NUMERIC_FEATURES, CATEGORICAL_FEATURES),
        "nasa_soil_humidity": score(merged, NUMERIC_FEATURES + SOIL_FEATURES, CATEGORICAL_FEATURES),
        "nasa_without_township": score(merged, NUMERIC_FEATURES + SOIL_FEATURES, ()),
    }
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
