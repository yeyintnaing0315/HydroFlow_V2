"""Train two XGBoost flood models on the saved chronological split.

`xgb-base` uses the 14 forecast features of the served HistGradientBoosting model.
`xgb-land` adds Open-Meteo daily soil moisture and reference evapotranspiration.
Those three fields are available from the archive API and the forecast API, so a
promoted model can be scored on a future day.

The train block fits the trees. Validation PR-AUC selects the candidate.
The validation block also fits the isotonic calibrator and the F1 threshold.
The untouched test block is scored once, and only for the selected candidate.
The served joblib is replaced only when that test PR-AUC is higher than the
published primary model.
"""

from __future__ import annotations

import json
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import average_precision_score
from xgboost import XGBClassifier

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml"))
sys.path.insert(0, str(ROOT / "backend"))

from app.services.calibrated_flood import CalibratedFloodModel  # noqa: E402
from retrain_served_model import (  # noqa: E402
    FEATURES,
    HUMIDITY_PATH,
    METADATA_PATH,
    MODEL_PATH,
    SPLIT_PATH,
    _best_threshold,
    _engineer,
    _metrics,
    _nasa_meteorology,
)

DAILY_PATH = ROOT / "data" / "processed" / "validated_daily.csv"
LAND_CACHE = ROOT / "data" / "external" / "open_meteo_land"
REPORT_PATH = ROOT / "ml" / "flood" / "xgboost_report.json"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
LAND_FEATURES = (
    "soil_moisture_0_to_7cm",
    "soil_moisture_7_to_28cm",
    "et0_fao_evapotranspiration",
)
# Daily archive names. Soil moisture is published as a daily mean of the hourly layers.
LAND_API_FIELDS = {
    "soil_moisture_0_to_7cm": "soil_moisture_0_to_7cm_mean",
    "soil_moisture_7_to_28cm": "soil_moisture_7_to_28cm_mean",
    "et0_fao_evapotranspiration": "et0_fao_evapotranspiration",
}
CHUNK_DAYS = 730


def _download_land(latitude: float, longitude: float, start: date, end: date) -> dict:
    daily_names = ",".join(LAND_API_FIELDS.values())
    times: list[str] = []
    columns: dict[str, list[float | None]] = {name: [] for name in LAND_FEATURES}
    cursor = start
    while cursor <= end:
        chunk_end = min(end, cursor + timedelta(days=CHUNK_DAYS - 1))
        query = urllib.parse.urlencode(
            {
                "latitude": latitude,
                "longitude": longitude,
                "start_date": cursor.isoformat(),
                "end_date": chunk_end.isoformat(),
                "daily": daily_names,
                "timezone": "UTC",
            }
        )
        request = urllib.request.Request(
            f"{ARCHIVE_URL}?{query}",
            headers={"User-Agent": "HydroFlow/2.0 (academic flood prototype)"},
        )
        payload = None
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=120) as response:
                    payload = json.load(response)
                break
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")[:400]
                last_error = RuntimeError(f"Open-Meteo archive HTTP {exc.code}: {body}")
                if exc.code < 500 and exc.code != 429:
                    raise last_error from exc
                time.sleep(2 * (attempt + 1))
            except Exception as exc:  # noqa: BLE001 - retry transient archive failures
                last_error = exc
                time.sleep(2 * (attempt + 1))
        if payload is None:
            raise RuntimeError(f"Open-Meteo archive failed for {latitude}, {longitude}") from last_error
        daily = payload["daily"]
        chunk_times = list(daily["time"])
        times.extend(chunk_times)
        for feature, api_name in LAND_API_FIELDS.items():
            series = daily[api_name]
            if len(series) != len(chunk_times):
                raise RuntimeError(f"Open-Meteo returned a short {api_name} series")
            columns[feature].extend(series)
        cursor = chunk_end + timedelta(days=1)
        time.sleep(0.35)
    return {
        "source": ARCHIVE_URL,
        "api_fields": LAND_API_FIELDS,
        "daily": {"time": times, **columns},
    }


def _land_frame(township_id: str, latitude: float, longitude: float, start: date, end: date) -> pd.DataFrame:
    LAND_CACHE.mkdir(parents=True, exist_ok=True)
    cache = LAND_CACHE / f"{township_id}.json"
    if cache.is_file():
        payload = json.loads(cache.read_text(encoding="utf-8"))
        print(f"Open-Meteo land cache {township_id}", flush=True)
    else:
        print(f"Open-Meteo land download {township_id}", flush=True)
        payload = _download_land(latitude, longitude, start, end)
        temporary = cache.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload), encoding="utf-8")
        temporary.replace(cache)
    daily = payload["daily"]
    frame = pd.DataFrame(
        {
            "township_id": township_id,
            "date": pd.to_datetime(daily["time"]),
            **{name: daily[name] for name in LAND_FEATURES},
        }
    )
    for name in LAND_FEATURES:
        frame[name] = pd.to_numeric(frame[name], errors="coerce")
    return frame


def _base_frame(daily: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    split = pd.read_csv(SPLIT_PATH, parse_dates=["date"])
    humidity = pd.read_csv(HUMIDITY_PATH, parse_dates=["date"])
    start = daily["date"].min().strftime("%Y%m%d")
    end = daily["date"].max().strftime("%Y%m%d")
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
    frame = daily.merge(
        humidity[["township_id", "date", "relative_humidity_pct"]],
        on=["township_id", "date"],
        how="left",
    )
    frame = frame.merge(nasa, on=["township_id", "date"], how="left")
    missing = frame["temperature_c"].isna() | frame["wind_speed_m_s"].isna() | frame["relative_humidity_pct"].isna()
    filled_rows = 0
    if missing.any():
        from retrain_served_model import _open_meteo_archive

        start_iso = daily["date"].min().date().isoformat()
        end_iso = min(daily["date"].max().date(), date.today() - timedelta(days=1)).isoformat()
        needed = set(frame.loc[missing, "township_id"])
        archives = []
        for row in locations.itertuples(index=False):
            if row.township_id not in needed:
                continue
            print(f"Open-Meteo archive gap fill {row.township_id}", flush=True)
            archives.append(
                _open_meteo_archive(row.township_id, float(row.lat), float(row.lng), start_iso, end_iso)
            )
        archive = pd.concat(archives, ignore_index=True)
        frame = frame.merge(archive, on=["township_id", "date"], how="left", suffixes=("", "_archive"))
        for column in ("temperature_c", "relative_humidity_pct", "wind_speed_m_s"):
            before = frame[column].isna()
            frame[column] = frame[column].fillna(frame[f"{column}_archive"])
            filled_rows += int((before & frame[column].notna()).sum())
            frame = frame.drop(columns=[f"{column}_archive"])
    engineered = _engineer(frame).merge(split, on=["date", "township_id"], how="inner")
    return engineered, filled_rows


def _assert_split(frame: pd.DataFrame) -> None:
    if not set(frame["split"]).issuperset({"train", "validation", "test"}):
        raise RuntimeError("Saved split is missing a train, validation, or test block")
    train_end = frame.loc[frame["split"] == "train", "date"].max()
    validation_start = frame.loc[frame["split"] == "validation", "date"].min()
    validation_end = frame.loc[frame["split"] == "validation", "date"].max()
    test_start = frame.loc[frame["split"] == "test", "date"].min()
    if not (train_end < validation_start and validation_end < test_start):
        raise RuntimeError("Saved split is not in chronological order")


def _make_model(scale_pos_weight: float) -> XGBClassifier:
    return XGBClassifier(
        n_estimators=300,
        max_depth=3,
        learning_rate=0.05,
        subsample=0.9,
        colsample_bytree=0.9,
        min_child_weight=5,
        reg_lambda=1.0,
        objective="binary:logistic",
        eval_metric="aucpr",
        scale_pos_weight=scale_pos_weight,
        tree_method="hist",
        random_state=42,
        n_jobs=4,
        verbosity=0,
    )


def _fit_candidate(name: str, frame: pd.DataFrame, features: tuple[str, ...]) -> dict:
    complete = frame.dropna(subset=list(features) + ["flood"]).copy()
    complete["flood"] = complete["flood"].astype(int)
    _assert_split(complete)
    train = complete["split"] == "train"
    validation = complete["split"] == "validation"
    y_train = complete.loc[train, "flood"]
    positives = int(y_train.sum())
    if positives == 0:
        raise RuntimeError(f"{name} has no flood rows in the train block")
    scale = float((y_train == 0).sum() / positives)
    model = _make_model(scale)
    model.fit(complete.loc[train, list(features)], y_train)
    raw_validation = model.predict_proba(complete.loc[validation, list(features)])[:, 1]
    y_validation = complete.loc[validation, "flood"]
    score = float(average_precision_score(y_validation, raw_validation))
    print(f"validation PR-AUC {name} {score:.4f} rows={len(complete)}", flush=True)
    return {
        "name": name,
        "features": features,
        "model": model,
        "frame": complete,
        "validation_pr_auc": score,
        "scale_pos_weight": scale,
        "rows": int(len(complete)),
        "rows_dropped": int(len(frame) - len(complete)),
    }


def _write_report(payload: dict) -> None:
    REPORT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "selected": payload.get("selected"),
                "joblib_replaced": payload.get("joblib_replaced"),
                "baseline_pr_auc": payload.get("baseline_pr_auc"),
                "test_pr_auc": None if payload.get("test") is None else payload["test"].get("pr_auc"),
            }
        ),
        flush=True,
    )


def main() -> None:
    if not DAILY_PATH.is_file() or not SPLIT_PATH.is_file():
        raise RuntimeError("validated_daily.csv or split_assignments.csv is missing")
    published = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    baseline_pr_auc = float(published["test"]["pr_auc"])
    daily = pd.read_csv(DAILY_PATH, parse_dates=["date"])
    engineered, filled_rows = _base_frame(daily)
    archive_end = min(daily["date"].max().date(), date.today() - timedelta(days=1))
    archive_start = daily["date"].min().date()
    locations = (
        daily.groupby("township_id", as_index=False)
        .agg(lat=("lat", "first"), lng=("lng", "first"))
        .sort_values("township_id")
    )
    land_error = None
    land_frames = []
    try:
        for row in locations.itertuples(index=False):
            land_frames.append(
                _land_frame(row.township_id, float(row.lat), float(row.lng), archive_start, archive_end)
            )
        land = pd.concat(land_frames, ignore_index=True)
        enriched = engineered.merge(land, on=["township_id", "date"], how="left")
    except Exception as exc:  # noqa: BLE001 - keep the base candidate if the archive fails
        land_error = str(exc)
        enriched = engineered
        print(f"land features unavailable: {exc}", flush=True)

    candidates = [_fit_candidate("xgb-base", enriched, FEATURES)]
    if land_error is None:
        candidates.append(_fit_candidate("xgb-land", enriched, FEATURES + LAND_FEATURES))
    selected = max(candidates, key=lambda item: item["validation_pr_auc"])

    validation_mask = selected["frame"]["split"] == "validation"
    test_mask = selected["frame"]["split"] == "test"
    features = list(selected["features"])
    raw_validation = selected["model"].predict_proba(selected["frame"].loc[validation_mask, features])[:, 1]
    y_validation = selected["frame"].loc[validation_mask, "flood"]
    calibrator = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    calibrator.fit(raw_validation, y_validation)
    served = CalibratedFloodModel(selected["model"], calibrator)
    validation_probability = served.predict_proba(selected["frame"].loc[validation_mask, features])[:, 1]
    threshold = _best_threshold(y_validation, validation_probability)
    validation_metrics = _metrics(y_validation, validation_probability, threshold)
    y_test = selected["frame"].loc[test_mask, "flood"]
    test_probability = served.predict_proba(selected["frame"].loc[test_mask, features])[:, 1]
    test_metrics = _metrics(y_test, test_probability, threshold)

    replaced = float(test_metrics["pr_auc"]) > baseline_pr_auc
    if replaced:
        hgb_model = MODEL_PATH.with_name("bago_flood_model_hgb.joblib")
        hgb_metadata = METADATA_PATH.with_name("bago_flood_model_hgb_metadata.json")
        if not hgb_model.is_file():
            shutil.copy2(MODEL_PATH, hgb_model)
        if not hgb_metadata.is_file():
            shutil.copy2(METADATA_PATH, hgb_metadata)
        metadata = {
            "selected_model": "xgboost",
            "candidate": selected["name"],
            "decision_threshold": threshold,
            "features": features,
            "scale_pos_weight": selected["scale_pos_weight"],
            "land_api_fields": LAND_API_FIELDS if selected["name"] == "xgb-land" else {},
            "operational_hindcast_start": "2010-01-01",
            "townships": sorted(selected["frame"].loc[selected["frame"]["split"] == "train", "township"].unique()),
            "label": "Observed relief flood flag. No synthetic flood rows were added.",
            "sources": {
                "rainfall": "Open-Meteo reanalysis precipitation already stored in validated_daily.csv",
                "discharge": "GloFAS river discharge via the Open-Meteo Flood API, stored in validated_daily.csv",
                "humidity": "NASA POWER RH2M from data/external/nasa_power_daily.csv",
                "temperature_wind": "NASA POWER T2M and WS2M, with Open-Meteo archive only where NASA is missing",
                "soil_moisture_and_et0": "Open-Meteo archive daily soil_moisture_*_mean and et0_fao_evapotranspiration",
                "open_meteo_filled_values": filled_rows,
            },
            "split_source": "data/processed/split_assignments.csv",
            "rows_with_complete_features": selected["rows"],
            "rows_dropped_for_missing_features": selected["rows_dropped"],
            "validation": validation_metrics,
            "test": test_metrics,
            "test_majority_class_accuracy": float((y_test == 0).mean()),
            "test_used_for_training_calibration_or_threshold": False,
            "replaced_model": "hist_gradient_boosting",
            "replaced_test_pr_auc": baseline_pr_auc,
        }
        joblib.dump(served, MODEL_PATH)
        METADATA_PATH.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    _write_report(
        {
            "selected": selected["name"],
            "selected_features": features,
            "validation_pr_auc_by_candidate": {
                item["name"]: item["validation_pr_auc"] for item in candidates
            },
            "candidate_rows": {item["name"]: item["rows"] for item in candidates},
            "scale_pos_weight": {item["name"]: item["scale_pos_weight"] for item in candidates},
            "land_error": land_error,
            "land_api_fields": LAND_API_FIELDS,
            "archive_start": archive_start.isoformat(),
            "archive_end": archive_end.isoformat(),
            "baseline_model": published.get("selected_model"),
            "baseline_pr_auc": baseline_pr_auc,
            "validation": validation_metrics,
            "test": test_metrics,
            "joblib_replaced": replaced,
            "test_used_for_training_calibration_or_threshold": False,
            "logistic_secondary_unchanged": True,
        }
    )


if __name__ == "__main__":
    main()
