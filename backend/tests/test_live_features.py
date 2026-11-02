from datetime import date

from app.services.live_features import features_on_or_after


def test_features_use_earlier_api_days_only_as_context() -> None:
    rows = features_on_or_after(
        [
            (date(2026, 9, 30), 10.0, 100.0),
            (date(2026, 10, 1), 5.0, 110.0),
            (date(2026, 10, 2), 0.0, 90.0),
        ],
        date(2026, 10, 1),
        "bago",
        17.3,
        96.4,
    )

    assert [row["date"] for row in rows] == [date(2026, 10, 1), date(2026, 10, 2)]
    assert rows[0]["rainfall_lag_1d_mm"] == 10.0
    assert rows[0]["rainfall_3d_mm"] == 15.0
    assert rows[0]["discharge_lag_1d_m3s"] == 100.0
    assert rows[1]["rainfall_7d_mm"] == 15.0
