import json
import os
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from app.services.allocation_baseline import census_features, relief_features
from app.services.allocation_baseline import cap_planning_headcount
from app.services.flood_history import impact_severity
from app.services.prediction import ModelUnavailableError

LOG_COUNT_CAP = float(np.log1p(1_000_000))

DEFAULT_PLANNING_RATIOS = {
    "shelter_kits_per_household": 1.0,
    "food_rations_per_person_3d": 3.0,
    "drinking_water_liters_per_person_day": 15.0,
    "planning_days": 3,
}

PRIORITY_WEIGHT = {"none": 0, "low": 1, "moderate": 2, "high": 3, "severe": 4}

RISK_TO_PRIORITY = {
    "severe": "severe",
    "high": "high",
    "moderate": "moderate",
    "low": "low",
}


def help_model_path() -> Path:
    default = Path(__file__).resolve().parents[3] / "artifacts" / "flood_help_pipeline.joblib"
    return Path(os.getenv("HELP_MODEL_PATH", default))


def help_metadata_path() -> Path:
    default = Path(__file__).resolve().parents[3] / "artifacts" / "help_model_metadata.json"
    return Path(os.getenv("HELP_MODEL_METADATA_PATH", default))


def _count(value: float) -> int:
    return int(max(0, round(float(value))))


def _magnitude(regressor: Any, frame: pd.DataFrame) -> float:
    raw = float(regressor.predict(frame)[0])
    return max(0.0, float(np.expm1(min(raw, LOG_COUNT_CAP))))


@lru_cache(maxsize=1)
def load_help_model() -> tuple[dict[str, Any], dict[str, Any]]:
    path = help_model_path()
    metadata = help_metadata_path()
    if not path.is_file() or not metadata.is_file():
        raise ModelUnavailableError("Flood-help model artifact or metadata not found")
    try:
        bundle = joblib.load(path)
        model_metadata = json.loads(metadata.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ModelUnavailableError("Flood-help model artifact could not be loaded") from exc
    required = ("classifier", "people_regressor", "households_regressor")
    if any(name not in bundle for name in required):
        raise ModelUnavailableError("Flood-help artifact is missing a model stage")
    if "threshold" not in model_metadata or "planning_ratios" not in model_metadata:
        raise ModelUnavailableError("Flood-help metadata is missing threshold or planning ratios")
    return bundle, model_metadata


def help_model_available() -> bool:
    try:
        load_help_model()
    except ModelUnavailableError:
        return False
    return True


def _township_label(township_name_en: str | None, township_id: str | None) -> str | None:
    if township_name_en and str(township_name_en).strip():
        return str(township_name_en).strip()
    if township_id and str(township_id).strip():
        return str(township_id).strip()
    return None


def _raise_priority(current: str, candidate: str) -> str:
    if PRIORITY_WEIGHT.get(candidate, 0) > PRIORITY_WEIGHT.get(current, 0):
        return candidate
    return current


def _pack_help_result(
    *,
    probability: float,
    threshold: float,
    people: int,
    households: int,
    ratios: dict[str, float],
    model_version: str,
    priority_hint: str | None = None,
) -> dict[str, float | int | bool | str]:
    priority = impact_severity(households, people)
    if priority_hint:
        priority = _raise_priority(priority, priority_hint)
    people, households = cap_planning_headcount(people, households)
    return {
        "help_probability": probability,
        "predicted_help": bool(probability >= threshold or people > 0),
        "expected_affected_people": people,
        "expected_households": households,
        "assistance_priority": priority,
        "shelter_kits": _count(households * float(ratios["shelter_kits_per_household"])),
        "food_rations_3d": _count(people * float(ratios["food_rations_per_person_3d"])),
        "drinking_water_liters_3d": _count(
            people
            * float(ratios["drinking_water_liters_per_person_day"])
            * float(ratios["planning_days"])
        ),
        "model_version": model_version,
    }


def _predict_help_ml(features: dict[str, float | str]) -> dict[str, float | int | bool | str]:
    bundle, metadata = load_help_model()
    try:
        frame = pd.DataFrame([features])
        probability = float(bundle["classifier"].predict_proba(frame)[:, 1][0])
        people = _count(probability * _magnitude(bundle["people_regressor"], frame))
        households = _count(probability * _magnitude(bundle["households_regressor"], frame))
        ratios = metadata["planning_ratios"]
        threshold = float(metadata["threshold"])
    except Exception as exc:
        raise ValueError("Flood-help model rejected prediction features") from exc
    return _pack_help_result(
        probability=probability,
        threshold=threshold,
        people=people,
        households=households,
        ratios=ratios,
        model_version=str(metadata.get("version", "flood-help-v1")),
    )


def predict_help_from_flood_and_inventory(
    features: dict[str, float | str],
    *,
    planning_date: date | None = None,
    township_name_en: str | None = None,
    township_id: str | None = None,
) -> dict[str, float | int | bool | str]:
    """Estimate assistance demand from flood risk, census, relief workbook, and archive days."""
    from app.services import prediction, risk
    from app.services._lookup_service import get_simulation_risk

    label = _township_label(township_name_en, township_id)
    priority_hint: str | None = None
    probability = 0.0
    flood_version = "flood-rules-fallback"

    if planning_date is not None and label:
        from app.services.topredict_impact import impact_for_township_date

        workbook = impact_for_township_date(label, planning_date)
        if workbook is not None:
            people = int(workbook["expected_affected_people"])
            households = int(workbook["expected_households"])
            priority_hint = impact_severity(households, people)
            probability = 0.9 if priority_hint in {"high", "severe"} else 0.55
            packed = _pack_help_result(
                probability=probability,
                threshold=0.5,
                people=people,
                households=households,
                ratios=DEFAULT_PLANNING_RATIOS,
                model_version="flood-help-topredict-workbook",
                priority_hint=priority_hint,
            )
            if "affected_group_a" in workbook and "affected_group_b" in workbook:
                packed["affected_group_a"] = int(workbook["affected_group_a"])
                packed["affected_group_b"] = int(workbook["affected_group_b"])
            return packed

        sim = get_simulation_risk(planning_date, township=label)
        if sim.get("is_flood_day"):
            people = int(sim.get("affected", 0) or 0)
            households = int(sim.get("households", 0) or 0)
            severity = str(sim.get("severity") or sim.get("risk_level") or "moderate")
            priority_hint = RISK_TO_PRIORITY.get(severity, severity)
            probability = 0.9 if severity in {"high", "severe"} else 0.5
            return _pack_help_result(
                probability=probability,
                threshold=0.5,
                people=people,
                households=households,
                ratios=DEFAULT_PLANNING_RATIOS,
                model_version="flood-help-archive-fallback",
                priority_hint=priority_hint,
            )

    try:
        probability, _predicted_flood, threshold, flood_version = prediction.predict(features)
    except (ModelUnavailableError, ValueError):
        threshold = 0.5
        probability = 0.0
    else:
        threshold = float(threshold)

    rainfall = float(features.get("rainfall_mm") or 0)
    discharge = float(features.get("river_discharge_m3s") or 0)
    _score, risk_level = risk.academic_risk_score(rainfall, discharge, probability)
    priority_hint = RISK_TO_PRIORITY.get(risk_level)

    census = census_features(township_name_en) if township_name_en else {"township_population": 0.0, "township_households": 0.0}
    relief = relief_features(township_name_en) if township_name_en else {
        "relief_baseline_households": 0.0,
        "relief_baseline_affected": 0.0,
    }

    baseline_people = float(relief["relief_baseline_affected"])
    if baseline_people <= 0 and census["township_population"] > 0:
        baseline_people = census["township_population"] * 0.08
    baseline_households = float(relief["relief_baseline_households"])
    if baseline_households <= 0 and census["township_households"] > 0:
        baseline_households = census["township_households"] * 0.08

    people = _count(probability * baseline_people)
    households = _count(probability * baseline_households)

    if risk_level in {"high", "severe"} and people <= 0 and baseline_people > 0:
        scale = 0.55 if risk_level == "high" else 0.85
        people = _count(baseline_people * scale)
        households = _count(baseline_households * scale)
        probability = max(probability, 0.75 if risk_level == "high" else 0.9)

    if census["township_population"] > 0:
        people = min(people, _count(census["township_population"]))

    return _pack_help_result(
        probability=float(probability),
        threshold=threshold,
        people=people,
        households=households,
        ratios=DEFAULT_PLANNING_RATIOS,
        model_version=f"flood-help-{flood_version}-fallback",
        priority_hint=priority_hint,
    )


def predict_help(
    features: dict[str, float | str],
    *,
    planning_date: date | None = None,
    township_name_en: str | None = None,
    township_id: str | None = None,
) -> dict[str, float | int | bool | str]:
    if help_model_available():
        try:
            return _predict_help_ml(features)
        except ValueError:
            pass
    return predict_help_from_flood_and_inventory(
        features,
        planning_date=planning_date,
        township_name_en=township_name_en,
        township_id=township_id,
    )
