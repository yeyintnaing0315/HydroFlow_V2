"""Train the secondary served flood model (logistic regression, same features as HGB)."""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, f1_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
DAILY_PATH = ROOT / "data" / "raw" / "bago_daily.csv"
NASA_DIR = ROOT / "data" / "external" / "nasa_power_hydro"
MODEL_PATH = ROOT / "ml" / "models" / "bago_flood_model_logistic.joblib"
METADATA_PATH = ROOT / "ml" / "models" / "bago_flood_model_logistic_metadata.json"

FEATURES = (
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
)
MODEL_VERSION = "baseline-logistic-v2-served"


def _engineer(frame: pd.DataFrame) -> pd.DataFrame:
    ordered = frame.sort_values(["township_id", "date"], kind="stable").copy()
    grouped = ordered.groupby("township_id", sort=False)
    rain = grouped["rainfall_mm"]
    discharge = grouped["river_discharge_m3s"]
    ordered["rainfall_1d_mm"] = ordered["rainfall_mm"]
    ordered["rainfall_3d_mm"] = rain.transform(lambda series: series.rolling(3, min_periods=3).sum())
    ordered["rainfall_7d_mm"] = rain.transform(lambda series: series.rolling(7, min_periods=7).sum())
    ordered["rainfall_14d_mm"] = rain.transform(lambda series: series.rolling(14, min_periods=14).sum())
    ordered["rainfall_30d_mm"] = rain.transform(lambda series: series.rolling(30, min_periods=30).sum())
    ordered["discharge_lag_1d_m3s"] = discharge.shift(1)
    ordered["discharge_lag_3d_mean_m3s"] = discharge.transform(
        lambda series: series.shift(1).rolling(3, min_periods=3).mean()
    )
    day = ordered["date"].dt.dayofyear
    ordered["day_of_year_sin"] = np.sin(2 * np.pi * day / 365.25)
    ordered["day_of_year_cos"] = np.cos(2 * np.pi * day / 365.25)
    ordered["latitude"] = ordered["lat"]
    ordered["longitude"] = ordered["lng"]
    return ordered


def _attach_meteorology(frame: pd.DataFrame) -> pd.DataFrame:
    pieces = []
    for township_id, group in frame.groupby("township_id", sort=False):
        merged = group.copy()
        nasa_path = NASA_DIR / f"{township_id}.csv"
        if nasa_path.is_file():
            nasa = pd.read_csv(nasa_path, parse_dates=["date"])
            merged = merged.merge(
                nasa[["date", "temperature_c", "relative_humidity_pct", "wind_speed_m_s"]],
                on="date",
                how="left",
            )
        else:
            merged["temperature_c"] = np.nan
            merged["relative_humidity_pct"] = np.nan
            merged["wind_speed_m_s"] = np.nan
        pieces.append(merged)
    return pd.concat(pieces, ignore_index=True)


def _chronological_split(dates: pd.Series) -> pd.Series:
    unique = pd.Series(sorted(dates.dt.normalize().unique()))
    n = len(unique)
    train_end = int(n * 0.7)
    validation_end = int(n * 0.85)
    train_dates = set(unique.iloc[:train_end])
    validation_dates = set(unique.iloc[train_end:validation_end])
    test_dates = set(unique.iloc[validation_end:])
    split = pd.Series("test", index=dates.index, dtype="object")
    split[dates.dt.normalize().isin(train_dates)] = "train"
    split[dates.dt.normalize().isin(validation_dates)] = "validation"
    return split


def _best_threshold(y_true: pd.Series, probability: np.ndarray) -> tuple[float, float]:
    best_threshold, best_f1 = 0.5, -1.0
    for threshold in np.linspace(0.01, 0.99, 99):
        predicted = probability >= threshold
        true = y_true.to_numpy() == 1
        tp = int((true & predicted).sum())
        fp = int((~true & predicted).sum())
        fn = int((true & ~predicted).sum())
        denominator = 2 * tp + fp + fn
        f1 = 0.0 if denominator == 0 else 2 * tp / denominator
        if f1 > best_f1:
            best_threshold, best_f1 = float(threshold), float(f1)
    return best_threshold, best_f1


def main() -> None:
    if not DAILY_PATH.is_file():
        raise FileNotFoundError(f"Missing training table: {DAILY_PATH}")
    daily = pd.read_csv(DAILY_PATH, parse_dates=["date"])
    frame = _attach_meteorology(daily)
    engineered = _engineer(frame)
    engineered["split"] = _chronological_split(engineered["date"])
    complete = engineered.dropna(subset=list(FEATURES) + ["flood"]).copy()
    complete["flood"] = complete["flood"].astype(int)

    pipeline = Pipeline(
        [
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
            (
                "classifier",
                LogisticRegression(
                    class_weight="balanced",
                    max_iter=2500,
                    random_state=42,
                    solver="lbfgs",
                ),
            ),
        ]
    )
    train_mask = complete["split"] == "train"
    validation_mask = complete["split"] == "validation"
    test_mask = complete["split"] == "test"
    x_train = complete.loc[train_mask, list(FEATURES)]
    y_train = complete.loc[train_mask, "flood"]
    x_validation = complete.loc[validation_mask, list(FEATURES)]
    y_validation = complete.loc[validation_mask, "flood"]
    x_test = complete.loc[test_mask, list(FEATURES)]
    y_test = complete.loc[test_mask, "flood"]

    pipeline.fit(x_train, y_train)
    validation_probability = pipeline.predict_proba(x_validation)[:, 1]
    threshold, validation_f1 = _best_threshold(y_validation, validation_probability)
    test_probability = pipeline.predict_proba(x_test)[:, 1]
    test_f1 = float(f1_score(y_test, test_probability >= threshold, zero_division=0))
    validation_pr = float(average_precision_score(y_validation, validation_probability))

    townships = sorted(complete["township"].dropna().unique().tolist())
    metadata = {
        "version": MODEL_VERSION,
        "selected_model": MODEL_VERSION,
        "model": "class-weighted LogisticRegression (alternate served model)",
        "features": list(FEATURES),
        "model_features": list(FEATURES),
        "decision_threshold": threshold,
        "threshold": threshold,
        "validation_f1_at_selected_threshold": validation_f1,
        "validation_pr_auc": validation_pr,
        "test_f1_at_selected_threshold": test_f1,
        "townships": townships,
        "training_rows": int(train_mask.sum()),
        "role": "secondary",
        "primary_model": "hist_gradient_boosting",
    }
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, MODEL_PATH)
    METADATA_PATH.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(
        f"Wrote {MODEL_PATH.name} threshold={threshold:.3f} "
        f"validation_f1={validation_f1:.3f} test_f1={test_f1:.3f}",
        flush=True,
    )


if __name__ == "__main__":
    main()
