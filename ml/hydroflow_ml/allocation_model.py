"""Multi-output SKU demand model trained from ToPredit relief history."""

from __future__ import annotations

import json
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.multioutput import MultiOutputRegressor

from .config import (
    ALLOCATION_METADATA_PATH,
    ALLOCATION_MODEL_PATH,
    RANDOM_STATE,
)
from .help_model import PLANNING_RATIOS
from .topredict_eda import parse_relief_events

ALLOCATION_VERSION = "allocation-v3"
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

# Column names match the inventory catalog: foods, clothing, kitchenware, utilities, fund.
SKU_SPECS: tuple[tuple[str, str, str | None, str, str], ...] = (
    ("foods_rice", "foods", "rice", "Rice", "bag"),
    ("foods_oil", "foods", "oil", "Oil", "bottle"),
    ("foods_canned_fish", "foods", "canned_fish", "Canned fish", "can"),
    ("utilities_blanket", "utilities", "blanket", "Blanket", "piece"),
    ("kitchenware_water_dipper", "kitchenware", "water_dipper", "Water dipper", "piece"),
    ("clothing_tshirt", "clothing", "tshirt", "T-shirt", "piece"),
    ("clothing_m_longyi", "clothing", "m_longyi", "Men longyi", "piece"),
    ("clothing_f_longyi", "clothing", "f_longyi", "Women longyi", "piece"),
    ("fund_mmk", "fund", None, "Fund", "mmk"),
)
SKU_COLUMNS = tuple(spec[0] for spec in SKU_SPECS)

LOG_CAP = float(np.log1p(1_000_000))


def _count(value: float) -> int:
    return int(max(0, round(float(value))))


def _impact_severity(households: int, people: int) -> str:
    score = max(0.0, float(households)) + max(0.0, float(people)) / 5.0
    if score >= 2000:
        return "severe"
    if score >= 500:
        return "high"
    if score >= 100:
        return "moderate"
    if score > 0:
        return "low"
    return "none"


def _planning_inputs(people: int, households: int) -> tuple[int, int, int]:
    food = people * int(PLANNING_RATIOS["food_rations_per_person_3d"])
    shelter = households * int(PLANNING_RATIOS["shelter_kits_per_household"])
    water_l = people * int(
        PLANNING_RATIOS["drinking_water_liters_per_person_day"] * PLANNING_RATIOS["planning_days"]
    )
    return food, shelter, water_l


def _rule_sku_quantities(people: int, households: int) -> dict[str, float]:
    """Same ratios as the planner fallback: rice bags are food rations divided by 3."""
    food, shelter, water_l = _planning_inputs(people, households)
    return {
        "foods_rice": float(_count(food / 3) if food else 0),
        "foods_oil": float(_count(water_l / 40) if water_l else 0),
        "foods_canned_fish": float(_count(households * 0.5) if households else 0),
        "utilities_blanket": float(shelter),
        "kitchenware_water_dipper": float(_count(water_l / 15) if water_l else 0),
        "clothing_tshirt": float(_count(people * 0.4) if people else 0),
        "clothing_m_longyi": float(_count(people * 0.3) if people else 0),
        "clothing_f_longyi": float(_count(people * 0.3) if people else 0),
        "fund_mmk": float(_count(people * 2500) if people else 0),
    }


def build_training_frame() -> pd.DataFrame:
    rows: list[dict[str, float | int]] = []
    for event in parse_relief_events():
        people = _count(event.affected_people)
        households = _count(event.households)
        if people <= 0 and households <= 0:
            continue
        priority = _impact_severity(households, people)
        probability = 0.9 if priority in {"high", "severe"} else 0.55
        food, shelter, water = _planning_inputs(people, households)
        sku = _rule_sku_quantities(people, households)
        rows.append(
            {
                "help_probability": probability,
                "expected_affected_people": people,
                "expected_households": households,
                "priority_weight": PRIORITY_WEIGHT.get(priority, 0),
                "food_rations_3d": food,
                "shelter_kits": shelter,
                "drinking_water_liters_3d": water,
                **{column: np.log1p(min(sku[column], 1_000_000)) for column in SKU_COLUMNS},
            }
        )
    if not rows:
        raise RuntimeError("ToPredit workbook produced no training rows")
    return pd.DataFrame(rows)


def train_allocation(
    model_path=ALLOCATION_MODEL_PATH,
    metadata_path=ALLOCATION_METADATA_PATH,
) -> tuple[Any, dict[str, Any]]:
    frame = build_training_frame()
    x_train = frame.loc[:, list(INPUT_FEATURES)]
    y_train = frame.loc[:, list(SKU_COLUMNS)]
    regressor = MultiOutputRegressor(
        HistGradientBoostingRegressor(random_state=RANDOM_STATE, max_depth=4, learning_rate=0.08)
    )
    regressor.fit(x_train, y_train)
    metadata = {
        "version": ALLOCATION_VERSION,
        "purpose": "Predict SKU quantities from flood-help planning features.",
        "training_rows": len(frame),
        "input_features": list(INPUT_FEATURES),
        "sku_columns": list(SKU_COLUMNS),
        "sku_catalog": [
            {
                "column": column,
                "category_code": category_code,
                "item_code": item_code,
                "name": name,
                "unit": unit,
            }
            for column, category_code, item_code, name, unit in SKU_SPECS
        ],
        "target_transform": "log1p",
        "source": "ToPredit_Excel_Data.xlsx relief totals with ratio-derived SKU labels",
    }
    model_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(regressor, model_path)
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return regressor, metadata
