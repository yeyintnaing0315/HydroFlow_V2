"""Retrain the served Bago flood model on downloaded observations.

Rainfall and GloFAS discharge come from the validated daily table
(Open-Meteo reanalysis and the Open-Meteo Flood API). Humidity comes from the
cached NASA POWER RH2M series. Temperature and 2 m wind are NASA POWER T2M and
WS2M, with Open-Meteo archive values used only on days NASA marks missing.
The existing chronological split is kept. The test block is not used for
fitting, calibration, or threshold selection.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.calibrated_flood import CalibratedFloodModel  # noqa: E402

DAILY_PATH = ROOT / "data" / "processed" / "validated_daily.csv"
SPLIT_PATH = ROOT / "data" / "processed" / "split_assignments.csv"
HUMIDITY_PATH = ROOT / "data" / "external" / "nasa_power_daily.csv"
NASA_CACHE = ROOT / "data" / "external" / "nasa_power_t2m_ws2m"
OPEN_METEO_CACHE = ROOT / "data" / "external" / "open_meteo_archive"
MODEL_PATH = ROOT / "ml" / "models" / "bago_flood_model.joblib"
METADATA_PATH = ROOT / "ml" / "models" / "bago_flood_model_metadata.json"

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


def _nasa_meteorology(township_id: str, latitude: float, longitude: float, start: str, end: str) -> pd.DataFrame:
    NASA_CACHE.mkdir(parents=True, exist_ok=True)
    cache = NASA_CACHE / f"{township_id}.json"
    if cache.exists():
        payload = json.loads(cache.read_text(encoding="utf-8"))
    else:
        query = urllib.parse.urlencode(
            {
                "parameters": "T2M,WS2M",
                "community": "AG",
                "longitude": longitude,
                "latitude": latitude,
                "start": start,
                "end": end,
                "format": "JSON",
                "time-standard": "UTC",
            }
        )
        last_error: Exception | None = None
        payload = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(
                    f"https://power.larc.nasa.gov/api/temporal/daily/point?{query}",
                    timeout=120,
                ) as response:
                    payload = json.load(response)
                break
            except Exception as exc:  # noqa: BLE001 - retry transient NASA failures
                last_error = exc
                time.sleep(2 * (attempt + 1))
        if payload is None:
            raise RuntimeError(f"NASA POWER failed for {township_id}") from last_error
        cache.write_text(json.dumps(payload), encoding="utf-8")
        time.sleep(0.5)
    values = payload["properties"]["parameter"]
    temperature = values["T2M"]
    wind = values["WS2M"]
    days = sorted(set(temperature) & set(wind))
    frame = pd.DataFrame(
        {
            "township_id": township_id,
            "date": pd.to_datetime(days, format="%Y%m%d"),
            "temperature_c": [temperature[day] for day in days],
            "wind_speed_m_s": [wind[day] for day in days],
        }
    )
    frame.loc[frame["temperature_c"] <= -999, "temperature_c"] = np.nan
    frame.loc[frame["wind_speed_m_s"] <= -999, "wind_speed_m_s"] = np.nan
    return frame


def _open_meteo_archive(township_id: str, latitude: float, longitude: float, start: str, end: str) -> pd.DataFrame:
    OPEN_METEO_CACHE.mkdir(parents=True, exist_ok=True)
    cache = OPEN_METEO_CACHE / f"{township_id}.json"
    if cache.exists():
        payload = json.loads(cache.read_text(encoding="utf-8"))
    else:
        query = urllib.parse.urlencode(
            {
                "latitude": latitude,
                "longitude": longitude,
                "start_date": start,
                "end_date": end,
                "daily": "temperature_2m_mean,relative_humidity_2m_mean,wind_speed_10m_mean",
                "wind_speed_unit": "ms",
                "timezone": "UTC",
            }
        )
        with urllib.request.urlopen(
            f"https://archive-api.open-meteo.com/v1/archive?{query}",
            timeout=120,
        ) as response:
            payload = json.load(response)
        cache.write_text(json.dumps(payload), encoding="utf-8")
        time.sleep(0.4)
    daily = payload["daily"]
    return pd.DataFrame(
        {
            "township_id": township_id,
            "date": pd.to_datetime(daily["time"]),
            "temperature_c": daily["temperature_2m_mean"],
            "relative_humidity_pct": daily["relative_humidity_2m_mean"],
            "wind_speed_m_s": daily["wind_speed_10m_mean"],
        }
    )


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


def _metrics(y_true: pd.Series, probability: np.ndarray, threshold: float) -> dict:
    predicted = probability >= threshold
    matrix = confusion_matrix(y_true, predicted, labels=[0, 1])
    return {
        "rows": int(len(y_true)),
        "flood_rows": int(y_true.sum()),
        "threshold": float(threshold),
        "accuracy": float(accuracy_score(y_true, predicted)),
        "precision": float(precision_score(y_true, predicted, zero_division=0)),
        "recall": float(recall_score(y_true, predicted, zero_division=0)),
        "f1": float(f1_score(y_true, predicted, zero_division=0)),
        "roc_auc": float(roc_auc_score(y_true, probability)),
        "pr_auc": float(average_precision_score(y_true, probability)),
        "confusion_matrix_tn_fp_fn_tp": [int(matrix[0, 0]), int(matrix[0, 1]), int(matrix[1, 0]), int(matrix[1, 1])],
        "probability_p50_non_flood": float(np.median(probability[y_true.to_numpy() == 0])),
        "probability_p95_non_flood": float(np.quantile(probability[y_true.to_numpy() == 0], 0.95)),
        "probability_p50_flood": float(np.median(probability[y_true.to_numpy() == 1])) if int(y_true.sum()) else None,
    }


def _best_threshold(y_true: pd.Series, probability: np.ndarray) -> float:
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
            best_threshold, best_f1 = float(threshold), f1
    return best_threshold


def _candidate(name: str, **kwargs) -> tuple[str, HistGradientBoostingClassifier]:
    model = HistGradientBoostingClassifier(
        learning_rate=0.05,
        max_iter=300,
        l2_regularization=1.0,
        early_stopping=True,
        random_state=42,
        **kwargs,
    )
    return name, model


def main() -> None:
    daily = pd.read_csv(DAILY_PATH, parse_dates=["date"])
    split = pd.read_csv(SPLIT_PATH, parse_dates=["date"])
    humidity = pd.read_csv(HUMIDITY_PATH, parse_dates=["date"])
    start = daily["date"].min().strftime("%Y%m%d")
    end = daily["date"].max().strftime("%Y%m%d")
    start_iso = daily["date"].min().date().isoformat()
    end_iso = daily["date"].max().date().isoformat()

    locations = (
        daily.groupby("township_id", as_index=False)
        .agg(lat=("lat", "first"), lng=("lng", "first"), township=("township", "first"))
        .sort_values("township_id")
    )
    meteorology = []
    for row in locations.itertuples(index=False):
        print(f"NASA POWER T2M/WS2M {row.township_id}", flush=True)
        meteorology.append(_nasa_meteorology(row.township_id, float(row.lat), float(row.lng), start, end))
    nasa = pd.concat(meteorology, ignore_index=True)

    frame = daily.merge(humidity[["township_id", "date", "relative_humidity_pct"]], on=["township_id", "date"], how="left")
    frame = frame.merge(nasa, on=["township_id", "date"], how="left")
    missing = frame["temperature_c"].isna() | frame["wind_speed_m_s"].isna() | frame["relative_humidity_pct"].isna()
    filled_rows = 0
    if missing.any():
        needed = set(frame.loc[missing, "township_id"])
        archives = []
        for row in locations.itertuples(index=False):
            if row.township_id not in needed:
                continue
            print(f"Open-Meteo archive gap fill {row.township_id}", flush=True)
            archives.append(_open_meteo_archive(row.township_id, float(row.lat), float(row.lng), start_iso, end_iso))
        archive = pd.concat(archives, ignore_index=True)
        frame = frame.merge(archive, on=["township_id", "date"], how="left", suffixes=("", "_archive"))
        for column in ("temperature_c", "relative_humidity_pct", "wind_speed_m_s"):
            before = frame[column].isna()
            frame[column] = frame[column].fillna(frame[f"{column}_archive"])
            filled_rows += int((before & frame[column].notna()).sum())
            frame = frame.drop(columns=[f"{column}_archive"])

    engineered = _engineer(frame)
    engineered = engineered.merge(split, on=["date", "township_id"], how="inner")
    complete = engineered.dropna(subset=list(FEATURES) + ["flood"]).copy()
    complete["flood"] = complete["flood"].astype(int)
    if not set(complete["split"]).issuperset({"train", "validation", "test"}):
        raise RuntimeError("Saved split is missing a train, validation, or test block")
    train_end = complete.loc[complete["split"] == "train", "date"].max()
    validation_start = complete.loc[complete["split"] == "validation", "date"].min()
    validation_end = complete.loc[complete["split"] == "validation", "date"].max()
    test_start = complete.loc[complete["split"] == "test", "date"].min()
    if not (train_end < validation_start and validation_end < test_start):
        raise RuntimeError("Saved split is not in chronological order")

    old_model = joblib.load(MODEL_PATH)
    dry_october = complete[
        (complete["flood"] == 0)
        & (complete["date"].dt.month == 10)
        & (complete["rainfall_1d_mm"] < 5)
        & (complete["discharge_lag_1d_m3s"] < 5)
    ]
    old_probability = old_model.predict_proba(dry_october[list(FEATURES)])[:, 1]
    print(
        "previous model dry October days "
        f"n={len(dry_october)} median={np.median(old_probability):.3f} "
        f"p95={np.quantile(old_probability, 0.95):.3f}",
        flush=True,
    )

    x_train = complete.loc[complete["split"] == "train", list(FEATURES)]
    y_train = complete.loc[complete["split"] == "train", "flood"]
    x_validation = complete.loc[complete["split"] == "validation", list(FEATURES)]
    y_validation = complete.loc[complete["split"] == "validation", "flood"]
    x_test = complete.loc[complete["split"] == "test", list(FEATURES)]
    y_test = complete.loc[complete["split"] == "test", "flood"]

    candidates = [
        _candidate("hgb-depth3", max_depth=3, min_samples_leaf=20),
        _candidate("hgb-depth3-balanced", max_depth=3, min_samples_leaf=20, class_weight="balanced"),
        _candidate("hgb-depth4", max_depth=4, min_samples_leaf=10),
    ]
    best_name = ""
    best_model = None
    best_score = -1.0
    for name, model in candidates:
        model.fit(x_train, y_train)
        raw = model.predict_proba(x_validation)[:, 1]
        score = float(average_precision_score(y_validation, raw))
        print(f"validation PR-AUC {name} {score:.4f}", flush=True)
        if score > best_score:
            best_name, best_model, best_score = name, model, score
    if best_model is None:
        raise RuntimeError("No candidate model was fit")

    raw_validation = best_model.predict_proba(x_validation)[:, 1]
    calibrator = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    calibrator.fit(raw_validation, y_validation)
    served = CalibratedFloodModel(best_model, calibrator)
    validation_probability = served.predict_proba(x_validation)[:, 1]
    threshold = _best_threshold(y_validation, validation_probability)
    validation_metrics = _metrics(y_validation, validation_probability, threshold)
    test_probability = served.predict_proba(x_test)[:, 1]
    test_metrics = _metrics(y_test, test_probability, threshold)
    majority_accuracy = float((y_test == 0).mean())

    metadata = {
        "selected_model": "hist_gradient_boosting",
        "candidate": best_name,
        "decision_threshold": threshold,
        "features": list(FEATURES),
        "extended_features": [
            "soil_moisture",
            "runoff",
            "chirps_rainfall_7d_mm",
            "hand_pct_lt_2m",
            "jrc_depth_100y_max_m",
            "worldcover_pct_built_floodplain",
        ],
        "operational_hindcast_start": "2010-01-01",
        "townships": sorted(complete.loc[complete["split"] == "train", "township"].unique()),
        "label": "Observed relief flood flag. No synthetic flood rows were added.",
        "sources": {
            "rainfall": "Open-Meteo reanalysis precipitation already stored in validated_daily.csv",
            "discharge": "GloFAS river discharge via the Open-Meteo Flood API, stored in validated_daily.csv",
            "humidity": "NASA POWER RH2M from data/external/nasa_power_daily.csv",
            "temperature_wind": "NASA POWER T2M and WS2M, with Open-Meteo archive only where NASA is missing",
            "open_meteo_filled_values": filled_rows,
        },
        "split_source": "data/processed/split_assignments.csv",
        "rows_with_complete_features": int(len(complete)),
        "rows_dropped_for_missing_features": int(len(engineered) - len(complete)),
        "validation": validation_metrics,
        "test": test_metrics,
        "test_majority_class_accuracy": majority_accuracy,
        "test_used_for_training_calibration_or_threshold": False,
        "previous_model_dry_october_median_probability": float(np.median(old_probability)),
    }
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(served, MODEL_PATH)
    METADATA_PATH.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps({"validation": validation_metrics, "test": test_metrics, "majority_accuracy": majority_accuracy}, indent=2))


if __name__ == "__main__":
    main()
