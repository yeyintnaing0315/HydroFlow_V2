"""Learned SKU demand from flood-help outputs."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from app.schemas.api import AllocationLineItem
from app.services.prediction import ModelUnavailableError

PRIORITY_WEIGHT = {"none": 0, "low": 1, "moderate": 2, "high": 3, "severe": 4}

INPUT_FEATURES = (
    "help_probability",
    "expected_affected_people",
    "expected_households",
    "priority_weight",
    "food_rations_3d",
    "shelter_kits",
    "drinking_water_liters_3d",
)

ALLOCATION_VERSION = "allocation-v3"

# Keys are training columns. Values are inventory category, item, name, and unit.
SKU_BY_COLUMN: dict[str, tuple[str, str | None, str, str]] = {
    "foods_rice": ("foods", "rice", "Rice", "bag"),
    "foods_oil": ("foods", "oil", "Oil", "bottle"),
    "foods_canned_fish": ("foods", "canned_fish", "Canned fish", "can"),
    "utilities_blanket": ("utilities", "blanket", "Blanket", "piece"),
    "kitchenware_water_dipper": ("kitchenware", "water_dipper", "Water dipper", "piece"),
    "clothing_tshirt": ("clothing", "tshirt", "T-shirt", "piece"),
    "clothing_m_longyi": ("clothing", "m_longyi", "Men longyi", "piece"),
    "clothing_f_longyi": ("clothing", "f_longyi", "Women longyi", "piece"),
    "fund_mmk": ("fund", None, "Fund", "mmk"),
}

LOG_CAP = float(np.log1p(1_000_000))


def allocation_model_path() -> Path:
    default = Path(__file__).resolve().parents[3] / "artifacts" / "allocation_pipeline.joblib"
    return Path(os.getenv("ALLOCATION_MODEL_PATH", default))


def allocation_metadata_path() -> Path:
    default = Path(__file__).resolve().parents[3] / "artifacts" / "allocation_model_metadata.json"
    return Path(os.getenv("ALLOCATION_METADATA_PATH", default))


@lru_cache(maxsize=1)
def load_allocation_model() -> tuple[Any, dict[str, Any]]:
    path = allocation_model_path()
    metadata_path = allocation_metadata_path()
    if not path.is_file() or not metadata_path.is_file():
        raise ModelUnavailableError("Allocation model artifact or metadata not found")
    try:
        pipeline = joblib.load(path)
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ModelUnavailableError("Allocation model artifact could not be loaded") from exc
    if "sku_columns" not in metadata:
        raise ModelUnavailableError("Allocation metadata is missing sku_columns")
    return pipeline, metadata


def allocation_model_available() -> bool:
    try:
        load_allocation_model()
    except ModelUnavailableError:
        return False
    return True


def _help_input_row(scored: dict[str, Any]) -> pd.DataFrame:
    priority = str(scored.get("assistance_priority", "none"))
    return pd.DataFrame(
        [
            {
                "help_probability": float(scored["help_probability"]),
                "expected_affected_people": int(scored["expected_affected_people"]),
                "expected_households": int(scored["expected_households"]),
                "priority_weight": PRIORITY_WEIGHT.get(priority, 0),
                "food_rations_3d": int(scored.get("food_rations_3d", 0)),
                "shelter_kits": int(scored.get("shelter_kits", 0)),
                "drinking_water_liters_3d": int(scored.get("drinking_water_liters_3d", 0)),
            }
        ]
    )


def _rules_fallback(scored: dict[str, Any]) -> tuple[list[AllocationLineItem], str]:
    from app.services.allocation_rules import line_items_from_help_rules

    return line_items_from_help_rules(scored), "allocation-rules-fallback"


def _items_from_model(
    pipeline: Any,
    metadata: dict[str, Any],
    scored: dict[str, Any],
) -> list[AllocationLineItem] | None:
    """Read quantities in metadata column order. Unknown catalogs return None."""
    if str(metadata.get("version")) != ALLOCATION_VERSION:
        return None
    columns = [str(column) for column in metadata.get("sku_columns", [])]
    if not columns or any(column not in SKU_BY_COLUMN for column in columns):
        return None
    features = [str(name) for name in metadata.get("input_features", INPUT_FEATURES)]
    if features != list(INPUT_FEATURES):
        return None
    try:
        row = _help_input_row(scored)
        raw = np.asarray(pipeline.predict(row.loc[:, features]), dtype=float)
    except (KeyError, TypeError, ValueError, IndexError):
        return None
    raw = np.clip(raw, 0.0, LOG_CAP).reshape(-1)
    if raw.size != len(columns):
        return None
    quantities = np.rint(np.expm1(raw))
    items: list[AllocationLineItem] = []
    for column, qty in zip(columns, quantities, strict=True):
        amount = float(qty)
        if amount <= 0:
            continue
        category_code, item_code, name, unit = SKU_BY_COLUMN[column]
        items.append(
            AllocationLineItem(
                category_code=category_code,
                item_code=item_code,
                name=name,
                unit=unit,
                requested=amount,
                allocated=0.0,
            )
        )
    return items


def predict_sku_demand(scored: dict[str, Any]) -> tuple[list[AllocationLineItem], str]:
    """Return line items and model version string."""
    fallback_items, fallback_version = _rules_fallback(scored)
    try:
        pipeline, metadata = load_allocation_model()
    except ModelUnavailableError:
        return fallback_items, fallback_version
    items = _items_from_model(pipeline, metadata, scored)
    if not items:
        return fallback_items, fallback_version
    return items, str(metadata.get("version", ALLOCATION_VERSION))
