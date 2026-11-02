from hydroflow_ml.topredict_eda import parse_relief_events


def test_topredict_includes_bago_2023_impact_row() -> None:
    events = parse_relief_events()
    bago = [
        event
        for event in events
        if event.township_name_en == "Bago" and event.affected_people >= 10_000
    ]
    assert bago, "expected a high-impact Bago relief row from ToPredit"
    assert bago[0].households >= 4000
