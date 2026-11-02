"""Train XGBoost on the 28 Bago townships using hydrology back to 2000.

Relief labels still start in 2021. Earlier days supply rolling history and the
monthly normals, and they are not labeled as non-flood. Townships with no
relief rows are not given synthetic zeros. Madauk is scored on the old test
block but is not fit, because it is outside the official 28.

The served model is replaced only when the selected candidate's untouched test
PR-AUC on the original 22 townships is higher than the published primary model.
"""

from __future__ import annotations

import json
import shutil
import sys
from datetime import date
from pathlib import Path

import joblib
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import average_precision_score

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml"))
sys.path.insert(0, str(ROOT / "ml" / "flood"))
sys.path.insert(0, str(ROOT / "backend"))

from app.services.calibrated_flood import CalibratedFloodModel  # noqa: E402
from retrain_served_model import FEATURES, METADATA_PATH, MODEL_PATH, _engineer  # noqa: E402
from train_xgboost import LAND_FEATURES, _best_threshold, _make_model, _metrics  # noqa: E402

MERGED_DIR = ROOT / "data" / "external" / "hydro_merged"
MANIFEST = ROOT / "data" / "external" / "bago28_locations.json"
VALIDATED = ROOT / "data" / "processed" / "validated_daily.csv"
SPLIT_PATH = ROOT / "data" / "processed" / "split_assignments.csv"
NORMALS_PATH = ROOT / "data" / "external" / "bago28_climate_normals.json"
REPORT_PATH = ROOT / "ml" / "flood" / "xgboost_bago28_report.json"
LABEL_ALIASES = {"okpho": "okpo", "pantaung": "padaung"}
ORIGINAL_22 = {
    "bago",
    "daik_u",
    "htantabin",
    "kawa",
    "kyauktaga",
    "madauk",
    "minhla",
    "monyo",
    "okpo",
    "oktwin",
    "padaung",
    "pyay",
    "pyu",
    "shwedaung",
    "shwegyin",
    "taungoo",
    "thanatpin",
    "thayarwady",
    "thegon",
    "waw",
    "yedashe",
    "zigon",
}
CLIMATE_FEATURES = (
    "rainfall_30d_anomaly",
    "discharge_anomaly",
    "soil_moisture_anomaly",
)
BASE_FEATURES = FEATURES + LAND_FEATURES


def _split_bounds(split: pd.DataFrame) -> tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp, pd.Timestamp]:
    train_end = split.loc[split["split"] == "train", "date"].max()
    validation_start = split.loc[split["split"] == "validation", "date"].min()
    validation_end = split.loc[split["split"] == "validation", "date"].max()
    test_start = split.loc[split["split"] == "test", "date"].min()
    if not (train_end < validation_start <= validation_end < test_start):
        raise RuntimeError("Saved split dates are not in chronological order")
    return train_end, validation_start, validation_end, test_start


def _assign_split(
    dates: pd.Series,
    train_end: pd.Timestamp,
    validation_start: pd.Timestamp,
    validation_end: pd.Timestamp,
    test_start: pd.Timestamp,
) -> pd.Series:
    assigned = pd.Series(pd.NA, index=dates.index, dtype="string")
    assigned.loc[dates <= train_end] = "train"
    assigned.loc[(dates >= validation_start) & (dates <= validation_end)] = "validation"
    assigned.loc[dates >= test_start] = "test"
    return assigned


def _load_hydro(manifest: list[dict]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for place in manifest:
        path = MERGED_DIR / f"{place['township_id']}.csv"
        if not path.is_file():
            raise RuntimeError(f"Missing hydrology file {path}")
        frame = pd.read_csv(path, parse_dates=["date"])
        frames.append(frame)
    hydro = pd.concat(frames, ignore_index=True)
    return hydro.sort_values(["township_id", "date"], kind="stable")


def _labels() -> pd.DataFrame:
    frame = pd.read_csv(VALIDATED, parse_dates=["date"], usecols=["date", "township_id", "flood"])
    frame["township_id"] = frame["township_id"].replace(LABEL_ALIASES)
    frame["flood"] = frame["flood"].astype(int)
    return frame


def _normals(history: pd.DataFrame) -> pd.DataFrame:
    columns = ["rainfall_30d_mm", "discharge_lag_1d_m3s", "soil_moisture_0_to_7cm"]
    grouped = history.groupby(["township_id", "month"], as_index=False)[columns].median()
    return grouped.rename(
        columns={
            "rainfall_30d_mm": "rainfall_30d_normal",
            "discharge_lag_1d_m3s": "discharge_normal",
            "soil_moisture_0_to_7cm": "soil_moisture_normal",
        }
    )


def _write_normals(normals: pd.DataFrame) -> None:
    payload: dict[str, dict[str, dict[str, float]]] = {}
    for row in normals.itertuples(index=False):
        township = payload.setdefault(str(row.township_id), {})
        township[str(int(row.month))] = {
            "rainfall_30d_mm": None if pd.isna(row.rainfall_30d_normal) else float(row.rainfall_30d_normal),
            "discharge_lag_1d_m3s": None if pd.isna(row.discharge_normal) else float(row.discharge_normal),
            "soil_moisture_0_to_7cm": None if pd.isna(row.soil_moisture_normal) else float(row.soil_moisture_normal),
        }
    NORMALS_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _fit_candidate(name: str, frame: pd.DataFrame, features: tuple[str, ...]) -> dict:
    complete = frame.dropna(subset=list(features) + ["flood"]).copy()
    train = complete["split"] == "train"
    validation = complete["split"] == "validation"
    y_train = complete.loc[train, "flood"].astype(int)
    positives = int(y_train.sum())
    if positives == 0:
        raise RuntimeError(f"{name} has no flood rows in the train block")
    scale = float((y_train == 0).sum() / positives)
    model = _make_model(scale)
    model.fit(complete.loc[train, list(features)], y_train)
    raw_validation = model.predict_proba(complete.loc[validation, list(features)])[:, 1]
    y_validation = complete.loc[validation, "flood"].astype(int)
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
    }


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    official = {str(place["township_id"]) for place in manifest if place.get("official", True)}
    if len(official) != 28:
        raise RuntimeError(f"Expected 28 official townships, found {len(official)}")
    split = pd.read_csv(SPLIT_PATH, parse_dates=["date"])
    train_end, validation_start, validation_end, test_start = _split_bounds(split)
    hydro = _load_hydro(manifest)
    weather_sources = {}
    if "weather_source" in hydro.columns:
        for township_id, values in hydro.groupby("township_id")["weather_source"]:
            present = [value for value in values.dropna().unique()]
            weather_sources[str(township_id)] = present[0] if present else "open-meteo-archive"
    hydro["lat"] = hydro["latitude"]
    hydro["lng"] = hydro["longitude"]
    engineered = _engineer(hydro)
    engineered["month"] = engineered["date"].dt.month
    history = engineered.loc[engineered["date"] <= train_end].copy()
    normals = _normals(history)
    _write_normals(normals)
    engineered = engineered.merge(normals, on=["township_id", "month"], how="left")
    engineered["rainfall_30d_anomaly"] = engineered["rainfall_30d_mm"] - engineered["rainfall_30d_normal"]
    engineered["discharge_anomaly"] = engineered["discharge_lag_1d_m3s"] - engineered["discharge_normal"]
    engineered["soil_moisture_anomaly"] = engineered["soil_moisture_0_to_7cm"] - engineered["soil_moisture_normal"]

    labels = _labels()
    labeled_ids = set(labels["township_id"]) - {"madauk"}
    missing_labels = sorted(official - labeled_ids)
    engineered = engineered.merge(labels, on=["date", "township_id"], how="inner")
    engineered["split"] = _assign_split(
        engineered["date"], train_end, validation_start, validation_end, test_start
    )
    engineered = engineered.dropna(subset=["split"]).copy()
    fit_rows = engineered.loc[engineered["township_id"].isin(official)].copy()
    comparable = engineered.loc[
        (engineered["split"] == "test") & (engineered["township_id"].isin(ORIGINAL_22))
    ].copy()

    candidates = [
        _fit_candidate("xgb-28", fit_rows, BASE_FEATURES),
        _fit_candidate("xgb-28-climate", fit_rows, BASE_FEATURES + CLIMATE_FEATURES),
    ]
    selected = max(candidates, key=lambda item: item["validation_pr_auc"])
    features = list(selected["features"])
    validation_mask = selected["frame"]["split"] == "validation"
    raw_validation = selected["model"].predict_proba(selected["frame"].loc[validation_mask, features])[:, 1]
    y_validation = selected["frame"].loc[validation_mask, "flood"].astype(int)
    calibrator = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    calibrator.fit(raw_validation, y_validation)
    served = CalibratedFloodModel(selected["model"], calibrator)
    validation_probability = served.predict_proba(selected["frame"].loc[validation_mask, features])[:, 1]
    threshold = _best_threshold(y_validation, validation_probability)
    validation_metrics = _metrics(y_validation, validation_probability, threshold)

    comparable_features = comparable.dropna(subset=features).copy()
    test_probability = served.predict_proba(comparable_features.loc[:, features])[:, 1]
    test_metrics = _metrics(comparable_features["flood"].astype(int), test_probability, threshold)

    published = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    baseline_pr_auc = float(published["test"]["pr_auc"])
    replaced = float(test_metrics["pr_auc"]) > baseline_pr_auc
    if replaced:
        backup_model = MODEL_PATH.with_name("bago_flood_model_hgb.joblib")
        backup_meta = METADATA_PATH.with_name("bago_flood_model_hgb_metadata.json")
        if not backup_model.is_file():
            shutil.copy2(MODEL_PATH, backup_model)
        if not backup_meta.is_file():
            shutil.copy2(METADATA_PATH, backup_meta)
        metadata = {
            "selected_model": "xgboost",
            "candidate": selected["name"],
            "decision_threshold": threshold,
            "features": features,
            "scale_pos_weight": selected["scale_pos_weight"],
            "townships": sorted(fit_rows.loc[fit_rows["split"] == "train", "township"].unique())
            if "township" in fit_rows.columns
            else sorted(official),
            "label": "Observed relief flood flag from 2021. Years 2000-2020 are hydrologic context only.",
            "climate_normals": str(NORMALS_PATH.relative_to(ROOT)).replace("\\", "/"),
            "climate_normal_end": str(train_end.date()),
            "split_source": "data/processed/split_assignments.csv",
            "rows_with_complete_features": selected["rows"],
            "validation": validation_metrics,
            "test": test_metrics,
            "test_scope": "original 22 townships after Okpho/Pantaung alias mapping, including Madauk",
            "test_used_for_training_calibration_or_threshold": False,
            "replaced_model": published.get("selected_model"),
            "replaced_test_pr_auc": baseline_pr_auc,
        }
        joblib.dump(served, MODEL_PATH)
        METADATA_PATH.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    report = {
        "selected": selected["name"],
        "selected_features": features,
        "validation_pr_auc_by_candidate": {item["name"]: item["validation_pr_auc"] for item in candidates},
        "candidate_rows": {item["name"]: item["rows"] for item in candidates},
        "scale_pos_weight": {item["name"]: item["scale_pos_weight"] for item in candidates},
        "official_townships": sorted(official),
        "labeled_official_townships": sorted(official & labeled_ids),
        "official_townships_without_labels": missing_labels,
        "weather_sources": weather_sources,
        "madauk_excluded_from_fit": True,
        "history_start": "2000-01-01",
        "train_end": str(train_end.date()),
        "validation_start": str(validation_start.date()),
        "validation_end": str(validation_end.date()),
        "test_start": str(test_start.date()),
        "comparable_test_rows": int(len(comparable_features)),
        "comparable_test_flood_rows": int(comparable_features["flood"].sum()),
        "baseline_model": published.get("selected_model"),
        "baseline_pr_auc": baseline_pr_auc,
        "validation": validation_metrics,
        "test": test_metrics,
        "joblib_replaced": replaced,
        "logistic_secondary_unchanged": True,
        "test_used_for_training_calibration_or_threshold": False,
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "selected": selected["name"],
                "joblib_replaced": replaced,
                "baseline_pr_auc": baseline_pr_auc,
                "test_pr_auc": test_metrics["pr_auc"],
                "test_f1": test_metrics["f1"],
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
