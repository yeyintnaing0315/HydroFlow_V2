from app.services.allocation_baseline import (
    census_features,
    merge_planning_baseline,
    relief_baseline_by_name_en,
    topredict_path,
)


def test_topredict_workbook_loads_township_totals() -> None:
    assert topredict_path().is_file()
    totals = relief_baseline_by_name_en()
    assert totals, "expected at least one township from ToPredit workbook"
    assert any(row["relief_baseline_households"] > 0 for row in totals.values())


def test_census_features_for_bago() -> None:
    features = census_features("Bago")
    assert features["township_population"] > 0
    assert features["township_households"] > 0


def test_merge_caps_affected_by_census_population() -> None:
    scored = {
        "expected_affected_people": 1_000_000,
        "help_probability": 0.5,
    }
    merged = merge_planning_baseline(scored, township_name_en="Bago", flood_probability=0.8, predicted_flood=True)
    assert merged["expected_affected_people"] == 1000
    assert merged["expected_affected_people"] <= merged["township_population"]
    assert merged["flood_probability"] == 0.8
    assert merged["predicted_flood"] == 1.0
