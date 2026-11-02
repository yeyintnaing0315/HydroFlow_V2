import numpy as np
import pytest

from app.services.allocation_prediction import INPUT_FEATURES, predict_sku_demand
from app.services.prediction import ModelUnavailableError


def _scored() -> dict:
    return {
        "help_probability": 0.6,
        "expected_affected_people": 80,
        "expected_households": 20,
        "assistance_priority": "severe",
        "food_rations_3d": 240,
        "shelter_kits": 20,
        "drinking_water_liters_3d": 720,
    }


def test_missing_artifact_uses_inventory_codes(monkeypatch: pytest.MonkeyPatch) -> None:
    def _missing() -> None:
        raise ModelUnavailableError("missing")

    monkeypatch.setattr("app.services.allocation_prediction.load_allocation_model", _missing)
    items, version = predict_sku_demand(_scored())
    by_code = {(item.category_code, item.item_code): item for item in items}
    assert version == "allocation-rules-fallback"
    assert by_code[("foods", "rice")].requested == 80
    assert by_code[("foods", "rice")].unit == "bag"
    assert by_code[("utilities", "blanket")].unit == "piece"
    assert by_code[("kitchenware", "water_dipper")].category_code == "kitchenware"
    assert by_code[("clothing", "tshirt")].category_code == "clothing"
    assert by_code[("fund", None)].unit == "mmk"
    assert ("utility", "blanket") not in by_code
    assert ("clothes", "tshirt") not in by_code


def test_quantities_follow_metadata_column_order(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Pipeline:
        def predict(self, frame):
            assert list(frame.columns) == list(INPUT_FEATURES)
            return np.log1p([[5, 9]])

    metadata = {
        "version": "allocation-v3",
        "input_features": list(INPUT_FEATURES),
        "sku_columns": ["foods_oil", "foods_rice"],
    }
    monkeypatch.setattr(
        "app.services.allocation_prediction.load_allocation_model",
        lambda: (_Pipeline(), metadata),
    )
    items, version = predict_sku_demand(_scored())
    by_code = {item.item_code: item for item in items}
    assert version == "allocation-v3"
    assert by_code["oil"].requested == 5
    assert by_code["oil"].category_code == "foods"
    assert by_code["oil"].unit == "bottle"
    assert by_code["rice"].requested == 9
    assert by_code["rice"].unit == "bag"


def test_old_catalog_falls_back_to_rules(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Pipeline:
        def predict(self, _frame):
            raise AssertionError("old catalog must not be scored")

    monkeypatch.setattr(
        "app.services.allocation_prediction.load_allocation_model",
        lambda: (
            _Pipeline(),
            {"version": "allocation-v2-topredict", "sku_columns": ["utility_blanket"], "input_features": list(INPUT_FEATURES)},
        ),
    )
    _items, version = predict_sku_demand(_scored())
    assert version == "allocation-rules-fallback"
