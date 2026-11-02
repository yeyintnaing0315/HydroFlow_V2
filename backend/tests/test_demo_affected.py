from datetime import date

from app.services.demo_affected import demo_affected_people


def test_demo_affected_is_stable_and_bounded() -> None:
    day = date(2023, 8, 8)
    value = demo_affected_people("bago", day, 19_322)
    assert value == demo_affected_people("bago", day, 19_322)
    assert 10 <= value <= 900


def test_demo_affected_zero_when_no_impact() -> None:
    assert demo_affected_people("bago", date(2023, 8, 8), 0) == 0
