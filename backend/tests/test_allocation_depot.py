from app.services.allocation import _depot_region


def test_depot_region_uses_longitude_split() -> None:
    assert _depot_region(17.5, 96.5) == "east"
    assert _depot_region(18.0, 95.0) == "west"
