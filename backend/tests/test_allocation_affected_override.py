from app.services.allocation_baseline import cap_planning_headcount, merge_planning_baseline


def test_cap_planning_headcount_does_not_force_1000() -> None:
    people, households = cap_planning_headcount(1525, 400)
    assert people == 1525
    assert households == 400


def test_merge_uses_full_estimate_under_census_cap() -> None:
    scored = {"expected_affected_people": 1525, "expected_households": 380}
    merged = merge_planning_baseline(scored, township_name_en="Yedashe")
    assert merged["expected_affected_people"] == 1525
