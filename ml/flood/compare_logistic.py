"""Train logistic regression on the same split and features as the served model.

The held-out test block is scored once. The served histogram model stays in
place. This script only writes the comparison and the secondary logistic file.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
DAILY_PATH = ROOT / "data" / "processed" / "validated_daily.csv"
_LOCAL_SPLIT = ROOT / "data" / "processed" / "split_assignments.csv"
_LEGACY_SPLIT = ROOT.parent / "HydroFlow_V1" / "data" / "processed" / "split_assignments.csv"
SPLIT_PATH = _LOCAL_SPLIT if _LOCAL_SPLIT.is_file() else _LEGACY_SPLIT
HUMIDITY_PATH = ROOT / "data" / "external" / "nasa_power_daily.csv"
NASA_CACHE = ROOT / "data" / "external" / "nasa_power_t2m_ws2m"
HGB_PATH = ROOT / "ml" / "models" / "bago_flood_model.joblib"
HGB_META = ROOT / "ml" / "models" / "bago_flood_model_metadata.json"
LOGISTIC_PATH = ROOT / "ml" / "models" / "bago_flood_model_logistic.joblib"
LOGISTIC_META = ROOT / "ml" / "models" / "bago_flood_model_logistic_metadata.json"
REPORT_PATH = ROOT / "ml" / "flood" / "model_comparison.json"

FEATURES = [
    "rainfall_1d_mm",
    "rainfall_3d_mm",
    "rainfall_7d_mm",
    "rainfall_14d_mm",
    "rainfall_30d_mm",
    "temperature_c",
    "relative_humidity_pct",
    "wind_speed_m_s",
    "latitude",
    "longitude",
    "day_of_year_sin",
    "day_of_year_cos",
    "discharge_lag_1d_m3s",
    "discharge_lag_3d_mean_m3s",
]


def _meteorology(township_id: str) -> pd.DataFrame | None:
    path = NASA_CACHE / f"{township_id}.json"
    if not path.is_file():
        return None
    values = json.loads(path.read_text(encoding="utf-8"))["properties"]["parameter"]
    days = sorted(set(values["T2M"]) & set(values["WS2M"]))
    frame = pd.DataFrame(
        {
            "township_id": township_id,
            "date": pd.to_datetime(days, format="%Y%m%d"),
            "temperature_c": [float(values["T2M"][day]) for day in days],
            "wind_speed_m_s": [float(values["WS2M"][day]) for day in days],
        }
    )
    frame.loc[frame["temperature_c"] <= -999, "temperature_c"] = np.nan
    frame.loc[frame["wind_speed_m_s"] <= -999, "wind_speed_m_s"] = np.nan
    return frame


def _frame() -> pd.DataFrame:
    daily = pd.read_csv(DAILY_PATH, parse_dates=["date"])
    humidity = pd.read_csv(HUMIDITY_PATH, parse_dates=["date"])
    weather = pd.concat(
        [item for item in (_meteorology(str(name)) for name in daily["township_id"].unique()) if item is not None],
        ignore_index=True,
    )
    split = pd.read_csv(SPLIT_PATH, parse_dates=["date"])
    frame = daily.merge(humidity[["township_id", "date", "relative_humidity_pct"]], on=["township_id", "date"], how="left")
    frame = frame.merge(weather, on=["township_id", "date"], how="left")
    frame = frame.merge(split, on=["date", "township_id"], how="inner")
    frame = frame.sort_values(["township_id", "date"], kind="stable")
    grouped = frame.groupby("township_id", sort=False)
    rain = grouped["rainfall_mm"]
    discharge = grouped["river_discharge_m3s"]
    frame["rainfall_1d_mm"] = frame["rainfall_mm"]
    frame["rainfall_3d_mm"] = rain.transform(lambda series: series.rolling(3, min_periods=3).sum())
    frame["rainfall_7d_mm"] = rain.transform(lambda series: series.rolling(7, min_periods=7).sum())
    frame["rainfall_14d_mm"] = rain.transform(lambda series: series.rolling(14, min_periods=14).sum())
    frame["rainfall_30d_mm"] = rain.transform(lambda series: series.rolling(30, min_periods=30).sum())
    frame["discharge_lag_1d_m3s"] = discharge.shift(1)
    frame["discharge_lag_3d_mean_m3s"] = discharge.transform(
        lambda series: series.shift(1).rolling(3, min_periods=3).mean()
    )
    day = frame["date"].dt.dayofyear
    frame["day_of_year_sin"] = np.sin(2 * np.pi * day / 365.25)
    frame["day_of_year_cos"] = np.cos(2 * np.pi * day / 365.25)
    frame["latitude"] = frame["lat"]
    frame["longitude"] = frame["lng"]
    return frame.dropna(subset=FEATURES + ["flood"]).copy()


def _metrics(y_true: pd.Series, probability: np.ndarray, threshold: float) -> dict:
    predicted = probability >= threshold
    labels = y_true.astype(int).to_numpy()
    matrix = confusion_matrix(labels, predicted.astype(int), labels=[0, 1])
    return {
        "rows": int(len(labels)),
        "flood_rows": int(labels.sum()),
        "threshold": float(threshold),
        "accuracy": float(accuracy_score(labels, predicted)),
        "precision": float(precision_score(labels, predicted, zero_division=0)),
        "recall": float(recall_score(labels, predicted, zero_division=0)),
        "f1": float(f1_score(labels, predicted, zero_division=0)),
        "roc_auc": float(roc_auc_score(labels, probability)),
        "pr_auc": float(average_precision_score(labels, probability)),
        "confusion_matrix_tn_fp_fn_tp": [int(value) for value in matrix.ravel()],
    }


def _best_threshold(y_true: pd.Series, probability: np.ndarray) -> float:
    best_threshold, best_f1 = 0.5, -1.0
    labels = y_true.astype(int).to_numpy()
    for threshold in np.linspace(0.01, 0.99, 99):
        predicted = probability >= threshold
        true = labels == 1
        tp = int((true & predicted).sum())
        fp = int((~true & predicted).sum())
        fn = int((true & ~predicted).sum())
        score = 0.0 if (2 * tp + fp + fn) == 0 else (2 * tp) / (2 * tp + fp + fn)
        if score > best_f1:
            best_threshold, best_f1 = float(threshold), score
    return best_threshold


def main() -> None:
    frame = _frame()
    train = frame["split"] == "train"
    validation = frame["split"] == "validation"
    test = frame["split"] == "test"
    pipeline = Pipeline(
        [
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
            (
                "classifier",
                LogisticRegression(
                    class_weight="balanced",
                    max_iter=2000,
                    solver="liblinear",
                ),
            ),
        ]
    )
    pipeline.fit(frame.loc[train, FEATURES], frame.loc[train, "flood"].astype(int))
    validation_probability = pipeline.predict_proba(frame.loc[validation, FEATURES])[:, 1]
    threshold = _best_threshold(frame.loc[validation, "flood"], validation_probability)
    test_probability = pipeline.predict_proba(frame.loc[test, FEATURES])[:, 1]
    logistic = _metrics(frame.loc[test, "flood"], test_probability, threshold)

    served = json.loads(HGB_META.read_text(encoding="utf-8"))["test"]
    hgb_model = joblib.load(HGB_PATH)
    hgb_probability = np.asarray(hgb_model.predict_proba(frame.loc[test, FEATURES])[:, 1], dtype=float)
    hgb_threshold = float(json.loads(HGB_META.read_text(encoding="utf-8"))["decision_threshold"])
    paired = _metrics(frame.loc[test, "flood"], hgb_probability, hgb_threshold)
    best = "hist_gradient_boosting" if paired["pr_auc"] >= logistic["pr_auc"] else "logistic_regression"
    report = {
        "test_block_only": True,
        "served_model_replaced": False,
        "best_for_rare_floods": best,
        "reason": "PR-AUC is the comparison used for rare flood days. Accuracy favors the model that predicts no flood.",
        "logistic_regression": logistic,
        "hist_gradient_boosting_rescored": paired,
        "hist_gradient_boosting_published": {
            "accuracy": served["accuracy"],
            "precision": served["precision"],
            "recall": served["recall"],
            "f1": served["f1"],
            "roc_auc": served["roc_auc"],
            "pr_auc": served["pr_auc"],
        },
    }
    joblib.dump(pipeline, LOGISTIC_PATH)
    LOGISTIC_META.write_text(
        json.dumps(
            {
                "version": "baseline-logistic-v2-served",
                "selected_model": "logistic_regression",
                "role": "secondary",
                "primary_model": "hist_gradient_boosting",
                "features": FEATURES,
                "decision_threshold": threshold,
                "test": logistic,
                "best_model": best,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
