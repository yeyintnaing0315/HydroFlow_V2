"""Retrain the Bago flood model when a relief label file already exists.

The chronological split is the saved split_assignments.csv beside that file.
No flood days are synthesized. The served joblib is replaced only when the
retrained model's test PR-AUC is greater than the current metadata value
(0.008 on the published test block). Raster downloads are not performed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml"))
sys.path.insert(0, str(ROOT / "backend"))

from app.services.calibrated_flood import CalibratedFloodModel  # noqa: E402
from flood.static_prior import (  # noqa: E402
    EAST_LON,
    centroid_river_distance_km,
    discover_label_path,
    load_river_points,
)

REPORT_PATH = ROOT / "ml" / "flood" / "retrain_report.json"
MODEL_PATH = ROOT / "ml" / "models" / "bago_flood_model.joblib"
METADATA_PATH = ROOT / "ml" / "models" / "bago_flood_model_metadata.json"
HUMIDITY_PATH = ROOT / "data" / "external" / "nasa_power_daily.csv"
NASA_CACHE = ROOT / "data" / "external" / "nasa_power_t2m_ws2m"
RIVER_POINTS = ROOT / "data" / "external" / "bago_river_points.csv"

BASE_FEATURES = (
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
EXTRA_FEATURES = ("river_distance_km", "rainfall_upstream_1d_mm")
FEATURES = BASE_FEATURES + EXTRA_FEATURES
BAND_CUTS = (0.25, 0.50, 0.75)


def _write(payload: dict) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({key: payload.get(key) for key in ("labels_found", "joblib_replaced", "test_pr_auc", "baseline_pr_auc", "error")}))


def _nasa_meteorology(township_id: str) -> pd.DataFrame | None:
    cache = NASA_CACHE / f"{township_id}.json"
    if not cache.is_file():
        return None
    payload = json.loads(cache.read_text(encoding="utf-8"))
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


def _upstream_column(frame: pd.DataFrame) -> tuple[pd.Series, int]:
    """Mean rainfall at same-basin townships north of each row.

    When no such township exists, the row keeps its own centroid rainfall.
    That centroid-only fallback is counted and written into the report.
    """
    locations = (
        frame.groupby("township_id", as_index=False)
        .agg(lat=("lat", "first"), lng=("lng", "first"))
        .set_index("township_id")
    )
    basins = {
        township_id: "sittaung_bago" if float(row.lng) >= EAST_LON else "ayeyarwady"
        for township_id, row in locations.iterrows()
    }
    pivot = frame.pivot_table(index="date", columns="township_id", values="rainfall_mm", aggfunc="first")
    lookup: dict[str, pd.Series | None] = {}
    fallback_ids: list[str] = []
    for township_id, row in locations.iterrows():
        others = [
            other
            for other, other_row in locations.iterrows()
            if other != township_id
            and basins[other] == basins[township_id]
            and float(other_row.lat) >= float(row.lat) + 0.15
            and other in pivot.columns
        ]
        if not others:
            lookup[township_id] = None
            fallback_ids.append(str(township_id))
        else:
            lookup[township_id] = pivot[others].mean(axis=1)

    def _value(item: pd.Series) -> float:
        series = lookup[item.township_id]
        if series is None or item.date not in series.index or pd.isna(series.loc[item.date]):
            return float(item.rainfall_mm)
        return float(series.loc[item.date])

    values = frame.apply(_value, axis=1)
    fallback_rows = int(frame["township_id"].isin(fallback_ids).sum())
    return values, fallback_rows


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
        "roc_auc": float(roc_auc_score(y_true, probability)) if y_true.nunique() > 1 else None,
        "pr_auc": float(average_precision_score(y_true, probability)) if int(y_true.sum()) else None,
        "brier": float(brier_score_loss(y_true, probability)),
        "confusion_matrix_tn_fp_fn_tp": [int(matrix[0, 0]), int(matrix[0, 1]), int(matrix[1, 0]), int(matrix[1, 1])],
    }


def _band_metrics(y_true: pd.Series, probability: np.ndarray) -> dict[str, dict[str, float]]:
    scores: dict[str, dict[str, float]] = {}
    for cut in BAND_CUTS:
        predicted = probability >= cut
        scores[f"{cut:.2f}"] = {
            "precision": float(precision_score(y_true, predicted, zero_division=0)),
            "recall": float(recall_score(y_true, predicted, zero_division=0)),
        }
    return scores


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


def _lead_pr_auc(frame: pd.DataFrame, model: CalibratedFloodModel, lead: int) -> float | None:
    shifted = frame.sort_values(["township_id", "date"], kind="stable").copy()
    lagged = shifted.groupby("township_id", sort=False)[list(FEATURES)].shift(lead)
    shifted[list(FEATURES)] = lagged
    test = shifted.loc[shifted["split"] == "test"].dropna(subset=list(FEATURES))
    if test.empty or int(test["flood"].sum()) == 0:
        return None
    probability = model.predict_proba(test[list(FEATURES)])[:, 1]
    return float(average_precision_score(test["flood"], probability))


def main() -> None:
    label_path = discover_label_path(ROOT)
    if label_path is None:
        _write(
            {
                "labels_found": False,
                "joblib_replaced": False,
                "error": "No validated_daily.csv or bago_daily.csv label file was found.",
            }
        )
        return
    split_candidates = (
        label_path.parent / "split_assignments.csv",
        ROOT / "data" / "processed" / "split_assignments.csv",
        ROOT.parent / "HydroFlow_V1" / "data" / "processed" / "split_assignments.csv",
    )
    split_path = next((path for path in split_candidates if path.is_file()), None)
    if split_path is None:
        _write(
            {
                "labels_found": True,
                "label_file": str(label_path),
                "joblib_replaced": False,
                "error": "split_assignments.csv was not found in HydroFlow V2 (data/processed) or the previous HydroFlow V1 tree.",
            }
        )
        return
    if not HUMIDITY_PATH.is_file():
        _write(
            {
                "labels_found": True,
                "label_file": str(label_path),
                "joblib_replaced": False,
                "error": "nasa_power_daily.csv is missing, so temperature training inputs are incomplete.",
            }
        )
        return

    daily = pd.read_csv(label_path, parse_dates=["date"])
    split = pd.read_csv(split_path, parse_dates=["date"])
    humidity = pd.read_csv(HUMIDITY_PATH, parse_dates=["date"])
    locations = (
        daily.groupby("township_id", as_index=False)
        .agg(lat=("lat", "first"), lng=("lng", "first"), township=("township", "first"))
        .sort_values("township_id")
    )
    meteorology = []
    missing_nasa = []
    for row in locations.itertuples(index=False):
        frame = _nasa_meteorology(str(row.township_id))
        if frame is None:
            missing_nasa.append(str(row.township_id))
        else:
            meteorology.append(frame)
    if not meteorology:
        _write(
            {
                "labels_found": True,
                "label_file": str(label_path),
                "joblib_replaced": False,
                "error": "NASA POWER temperature cache is missing for every township.",
                "missing_nasa": missing_nasa,
            }
        )
        return
    nasa = pd.concat(meteorology, ignore_index=True)
    frame = daily.merge(
        humidity[["township_id", "date", "relative_humidity_pct"]],
        on=["township_id", "date"],
        how="left",
    )
    frame = frame.merge(nasa, on=["township_id", "date"], how="left")
    engineered = _engineer(frame)
    rivers = load_river_points(RIVER_POINTS)
    distance = {
        str(row.township_id): centroid_river_distance_km(float(row.lat), float(row.lng), rivers)
        for row in locations.itertuples(index=False)
    }
    engineered["river_distance_km"] = engineered["township_id"].map(distance)
    upstream, fallback_rows = _upstream_column(engineered)
    engineered["rainfall_upstream_1d_mm"] = upstream
    engineered = engineered.merge(split, on=["date", "township_id"], how="inner")
    complete = engineered.dropna(subset=list(FEATURES) + ["flood"]).copy()
    complete["flood"] = complete["flood"].astype(int)
    if not {"train", "validation", "test"}.issubset(set(complete["split"])):
        raise RuntimeError("Saved split is missing a train, validation, or test block")

    x_train = complete.loc[complete["split"] == "train", list(FEATURES)]
    y_train = complete.loc[complete["split"] == "train", "flood"]
    x_validation = complete.loc[complete["split"] == "validation", list(FEATURES)]
    y_validation = complete.loc[complete["split"] == "validation", "flood"]
    x_test = complete.loc[complete["split"] == "test", list(FEATURES)]
    y_test = complete.loc[complete["split"] == "test", "flood"]

    best_name = ""
    best_model = None
    best_score = -1.0
    validation_scores: dict[str, float] = {}
    for name, model in (
        _candidate("hgb-depth3", max_depth=3, min_samples_leaf=20),
        _candidate("hgb-depth3-balanced", max_depth=3, min_samples_leaf=20, class_weight="balanced"),
        _candidate("hgb-depth4", max_depth=4, min_samples_leaf=10),
    ):
        model.fit(x_train, y_train)
        raw = model.predict_proba(x_validation)[:, 1]
        score = float(average_precision_score(y_validation, raw))
        validation_scores[name] = score
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
    baseline = float(json.loads(METADATA_PATH.read_text(encoding="utf-8"))["test"]["pr_auc"])
    test_pr_auc = test_metrics["pr_auc"]
    replaced = test_pr_auc is not None and float(test_pr_auc) > baseline
    report = {
        "labels_found": True,
        "label_file": str(label_path),
        "split_file": str(split_path),
        "joblib_replaced": replaced,
        "baseline_pr_auc": baseline,
        "test_pr_auc": test_pr_auc,
        "candidate": best_name,
        "features": list(FEATURES),
        "upstream_fallback_rows": fallback_rows,
        "upstream_note": (
            "rainfall_upstream_1d_mm is the mean of same-basin townships at least "
            "0.15 degrees north. Rows with no such neighbor use centroid rainfall."
        ),
        "missing_nasa_cache": missing_nasa,
        "missing_rasters": [
            "JRC global river flood hazard v2.1",
            "Copernicus DEM GLO-30 or FABDEM",
            "MERIT Hydro",
            "ESA WorldCover",
            "HydroBASINS",
        ],
        "rows_with_complete_features": int(len(complete)),
        "validation_pr_auc_by_candidate": validation_scores,
        "validation": validation_metrics,
        "test": test_metrics,
        "test_band_precision_recall": _band_metrics(y_test, test_probability),
        "lead_1_test_pr_auc": _lead_pr_auc(complete, served, 1),
        "lead_3_test_pr_auc": _lead_pr_auc(complete, served, 3),
        "test_used_for_training_calibration_or_threshold": False,
    }
    if replaced:
        metadata = {
            "selected_model": "hist_gradient_boosting",
            "candidate": best_name,
            "decision_threshold": threshold,
            "features": list(FEATURES),
            "townships": sorted(complete.loc[complete["split"] == "train", "township"].unique()),
            "label": "Observed relief flood flag. No synthetic flood rows were added.",
            "sources": {
                "rainfall": f"Open-Meteo reanalysis precipitation already stored in {label_path.name}",
                "discharge": f"GloFAS river discharge stored in {label_path.name}",
                "humidity": "NASA POWER RH2M from data/external/nasa_power_daily.csv",
                "temperature_wind": "NASA POWER T2M and WS2M cache only; no live download in this retrain",
                "static_prior": "Centroid distance to data/external/bago_river_points.csv",
                "upstream_rainfall": "Mean of northern same-basin townships in the label file, else centroid rainfall",
            },
            "split_source": str(split_path),
            "rows_with_complete_features": int(len(complete)),
            "validation": validation_metrics,
            "test": test_metrics,
            "test_used_for_training_calibration_or_threshold": False,
            "previous_test_pr_auc": baseline,
        }
        MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        import joblib

        joblib.dump(served, MODEL_PATH)
        METADATA_PATH.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    _write(report)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        _write({"labels_found": discover_label_path(ROOT) is not None, "joblib_replaced": False, "error": str(exc)})
        raise
