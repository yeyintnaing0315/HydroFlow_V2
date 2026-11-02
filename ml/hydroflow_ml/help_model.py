"""Flood-help model: assistance demand from hydrologic features only."""

from __future__ import annotations

import json

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.metrics import (
    average_precision_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline

from .config import (
    HELP_METADATA_PATH,
    HELP_METRICS_PATH,
    HELP_MODEL_PATH,
    HELP_PREDICTIONS_PATH,
    IMPACT_COLUMNS,
    MODEL_FEATURES,
    RANDOM_STATE,
)
from .model import make_pipeline, select_threshold
from .severity import academic_impact_severity
from .splits import assert_temporal_order, chronological_split

HELP_VERSION = "flood-help-v2"
RIDGE_ALPHA = 1.0
LOG_COUNT_CAP = float(np.log1p(1_000_000))
PLANNING_RATIOS = {
    "shelter_kits_per_household": 1.0,
    "food_rations_per_person_3d": 3.0,
    "drinking_water_liters_per_person_day": 15.0,
    "planning_days": 3,
}


def make_magnitude_pipeline() -> Pipeline:
    """Same preprocessing as the flood classifier, with a Ridge magnitude head."""
    source = make_pipeline()
    return Pipeline(source.steps[:-1] + [("regressor", Ridge(alpha=RIDGE_ALPHA))])


def assistance_frame(data: pd.DataFrame) -> pd.DataFrame:
    missing = [column for column in IMPACT_COLUMNS if column not in data.columns]
    if missing:
        raise ValueError(f"Flood-help training requires impact columns: {missing}")
    households = pd.to_numeric(data["households"], errors="coerce").fillna(0).clip(lower=0)
    people = pd.to_numeric(data["affected_people"], errors="coerce").fillna(0).clip(lower=0)
    labels = pd.DataFrame(
        {
            "help_needed": ((households > 0) | (people > 0)).astype(int),
            "households": households,
            "affected_people": people,
        },
        index=data.index,
    )
    return labels


def _magnitude(regressor: Pipeline, features: pd.DataFrame) -> np.ndarray:
    raw = np.clip(regressor.predict(features), 0.0, LOG_COUNT_CAP)
    return np.expm1(raw)


def _coefficient_rows(pipeline: Pipeline, step: str) -> list[dict[str, float | str]]:
    names = pipeline.named_steps["preprocess"].get_feature_names_out()
    estimator = pipeline.named_steps[step]
    values = estimator.coef_[0] if step == "classifier" else estimator.coef_
    rows = (
        {"feature": str(name), "coefficient": float(value)}
        for name, value in zip(names, values)
    )
    return sorted(rows, key=lambda row: abs(float(row["coefficient"])), reverse=True)


def train_help(
    data: pd.DataFrame,
    model_path=None,
    metadata_path=None,
) -> tuple[dict, dict, pd.Series]:
    model_path = HELP_MODEL_PATH if model_path is None else model_path
    metadata_path = HELP_METADATA_PATH if metadata_path is None else metadata_path
    forbidden = (set(IMPACT_COLUMNS) | {"flood", "help_needed"}) & set(MODEL_FEATURES)
    if forbidden:
        raise RuntimeError(f"Help model features include leakage columns: {sorted(forbidden)}")

    labels = assistance_frame(data)
    split = chronological_split(data)
    assert_temporal_order(data, split)
    train_mask = split == "train"
    validation_mask = split == "validation"
    help_train = train_mask & (labels["help_needed"] == 1)
    if int(help_train.sum()) == 0:
        raise RuntimeError("Train block has no assistance rows for the magnitude models")

    features = list(MODEL_FEATURES)
    classifier = make_pipeline()
    classifier.fit(data.loc[train_mask, features], labels.loc[train_mask, "help_needed"])
    validation_probability = classifier.predict_proba(data.loc[validation_mask, features])[:, 1]
    threshold, validation_f1 = select_threshold(
        labels.loc[validation_mask, "help_needed"], validation_probability
    )

    people_regressor = make_magnitude_pipeline()
    households_regressor = make_magnitude_pipeline()
    people_regressor.fit(
        data.loc[help_train, features],
        np.log1p(labels.loc[help_train, "affected_people"]),
    )
    households_regressor.fit(
        data.loc[help_train, features],
        np.log1p(labels.loc[help_train, "households"]),
    )

    def _seen(pipeline: Pipeline) -> int:
        return int(
            pipeline.named_steps["preprocess"]
            .named_transformers_["numeric"]
            .named_steps["scale"]
            .n_samples_seen_
        )

    split_summary = {
        name: {
            "rows": int((split == name).sum()),
            "help_rows": int(labels.loc[split == name, "help_needed"].sum()),
            "start": pd.to_datetime(data.loc[split == name, "date"]).min().date().isoformat(),
            "end": pd.to_datetime(data.loc[split == name, "date"]).max().date().isoformat(),
        }
        for name in ("train", "validation", "test")
    }
    if _seen(classifier) != split_summary["train"]["rows"]:
        raise RuntimeError("Help classifier saw a different row count than the train block")
    if _seen(people_regressor) != int(help_train.sum()):
        raise RuntimeError("Magnitude model saw rows outside the train assistance block")

    bundle = {
        "classifier": classifier,
        "people_regressor": people_regressor,
        "households_regressor": households_regressor,
    }
    metadata = {
        "model": "two-stage flood help: class-weighted LogisticRegression plus Ridge magnitude",
        "version": HELP_VERSION,
        "purpose": (
            "Estimate whether a township-day needs humanitarian assistance and the expected "
            "households and affected people."
        ),
        "class_weight": "balanced",
        "random_state": RANDOM_STATE,
        "ridge_alpha": RIDGE_ALPHA,
        "model_features": features,
        "explicitly_excluded_leakage_fields": ["households", "affected_people", "flood"],
        "targets": {
            "help_needed": "1 when recorded households or affected_people is greater than zero",
            "affected_people": "log1p Ridge fit only on train rows with help_needed = 1",
            "households": "log1p Ridge fit only on train rows with help_needed = 1",
        },
        "fitted_classifier_rows": split_summary["train"]["rows"],
        "fitted_magnitude_rows": int(help_train.sum()),
        "test_rows_excluded_from_fit": split_summary["test"]["rows"],
        "threshold": threshold,
        "threshold_selection": "Maximum help-class F1 on chronological validation block only",
        "validation_f1_at_selected_threshold": validation_f1,
        "planning_ratios": PLANNING_RATIOS,
        "planning_note": (
            "Shelter, food, and water figures multiply expected counts by fixed planning ratios. "
            "They are illustrations for the academic dashboard, not optimized allocations."
        ),
        "severity_note": (
            "Assistance priority applies the retrospective severity rule to expected counts. "
            "Priority is not a learned class."
        ),
        "flood_occurrence_model": (
            "Unchanged. This artifact does not replace flood_logistic_pipeline.joblib."
        ),
        "split": split_summary,
        "classifier_coefficients": _coefficient_rows(classifier, "classifier"),
        "people_coefficients": _coefficient_rows(people_regressor, "regressor"),
        "household_coefficients": _coefficient_rows(households_regressor, "regressor"),
    }
    model_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, model_path)
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return bundle, metadata, split


def score_help_features(
    features: pd.DataFrame,
    bundle: dict,
    metadata: dict,
) -> pd.DataFrame:
    missing = sorted(set(MODEL_FEATURES) - set(features.columns))
    if missing:
        raise ValueError(f"Missing model features: {missing}")
    matrix = features.loc[:, list(MODEL_FEATURES)]
    probability = bundle["classifier"].predict_proba(matrix)[:, 1]
    people_if_help = _magnitude(bundle["people_regressor"], matrix)
    households_if_help = _magnitude(bundle["households_regressor"], matrix)
    ratios = metadata.get("planning_ratios", PLANNING_RATIOS)
    people = np.rint(np.clip(probability * people_if_help, 0, None)).astype(int)
    households = np.rint(np.clip(probability * households_if_help, 0, None)).astype(int)
    water_days = float(ratios["drinking_water_liters_per_person_day"]) * float(ratios["planning_days"])
    scored = pd.DataFrame(
        {
            "help_probability": probability,
            "predicted_help": (probability >= float(metadata["threshold"])).astype(int),
            "expected_affected_people": people,
            "expected_households": households,
            "assistance_priority": academic_impact_severity(
                pd.Series(households, index=features.index),
                pd.Series(people, index=features.index),
            ).astype(str),
            "shelter_kits": np.rint(households * float(ratios["shelter_kits_per_household"])).astype(int),
            "food_rations_3d": np.rint(people * float(ratios["food_rations_per_person_3d"])).astype(int),
            "drinking_water_liters_3d": np.rint(people * water_days).astype(int),
            "threshold": float(metadata["threshold"]),
        },
        index=features.index,
    )
    return scored


def predict_help_rows(
    data: pd.DataFrame,
    model_path=None,
    metadata_path=None,
) -> pd.DataFrame:
    """Score engineered rows. Impact fields are never read."""
    model_path = HELP_MODEL_PATH if model_path is None else model_path
    metadata_path = HELP_METADATA_PATH if metadata_path is None else metadata_path
    bundle = joblib.load(model_path)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    scored = score_help_features(data, bundle, metadata)
    output_columns = [column for column in ("date", "township_id") if column in data.columns]
    output = data.loc[:, output_columns].copy()
    return pd.concat([output.reset_index(drop=True), scored.reset_index(drop=True)], axis=1)


def _block_metrics(labels: pd.DataFrame, scored: pd.DataFrame) -> dict:
    y_true = labels["help_needed"].astype(int)
    probability = scored["help_probability"]
    predicted = scored["predicted_help"].astype(int)
    metrics: dict = {
        "threshold": float(scored["threshold"].iloc[0]),
        "rows": int(len(y_true)),
        "help_rows": int(y_true.sum()),
        "precision": float(precision_score(y_true, predicted, zero_division=0)),
        "recall": float(recall_score(y_true, predicted, zero_division=0)),
        "f1": float(f1_score(y_true, predicted, zero_division=0)),
        "predicted_positive_rows": int(predicted.sum()),
        "expected_affected_people_mae": float(
            np.mean(np.abs(scored["expected_affected_people"] - labels["affected_people"]))
        ),
        "expected_households_mae": float(
            np.mean(np.abs(scored["expected_households"] - labels["households"]))
        ),
    }
    positive = y_true == 1
    if int(positive.sum()) > 0:
        metrics["positive_people_mae"] = float(
            np.mean(
                np.abs(
                    scored.loc[positive, "expected_affected_people"]
                    - labels.loc[positive, "affected_people"]
                )
            )
        )
    if y_true.nunique() > 1:
        metrics["pr_auc_average_precision"] = float(average_precision_score(y_true, probability))
        metrics["roc_auc"] = float(roc_auc_score(y_true, probability))
    else:
        metrics["pr_auc_average_precision"] = None
        metrics["roc_auc"] = None
    return metrics


def evaluate_help(
    data: pd.DataFrame,
    model_path=None,
    metadata_path=None,
    metrics_path=None,
    predictions_path=None,
) -> dict:
    model_path = HELP_MODEL_PATH if model_path is None else model_path
    metadata_path = HELP_METADATA_PATH if metadata_path is None else metadata_path
    metrics_path = HELP_METRICS_PATH if metrics_path is None else metrics_path
    predictions_path = HELP_PREDICTIONS_PATH if predictions_path is None else predictions_path
    labels = assistance_frame(data)
    split = chronological_split(data)
    scored = predict_help_rows(data, model_path=model_path, metadata_path=metadata_path)
    results: dict = {
        "model_path": str(model_path),
        "version": HELP_VERSION,
        "threshold_source": "chronological validation maximum help-class F1",
        "test_data_was_used_for_training_or_threshold_selection": False,
        "retrained_during_evaluation": False,
    }
    frames = []
    for block in ("validation", "test"):
        mask = (split == block).to_numpy()
        block_labels = labels.loc[split == block].reset_index(drop=True)
        block_scored = scored.loc[mask].reset_index(drop=True)
        results[block] = _block_metrics(block_labels, block_scored)
        frame = block_scored.copy()
        frame["split"] = block
        frame["actual_help"] = block_labels["help_needed"].to_numpy()
        frames.append(frame)
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    predictions_path.parent.mkdir(parents=True, exist_ok=True)
    pd.concat(frames, ignore_index=True).to_csv(predictions_path, index=False)
    return results
