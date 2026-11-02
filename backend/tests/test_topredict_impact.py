from datetime import date

from app.services.topredict_impact import impact_for_township_date


def test_bago_2023_08_08_matches_workbook_row() -> None:
    impact = impact_for_township_date("Bago", date(2023, 8, 8))
    assert impact is not None
    assert impact["expected_affected_people"] == 19322
    assert impact["expected_households"] == 4521
