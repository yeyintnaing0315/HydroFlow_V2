from datetime import date

from app.services.daily_catalog import calendar_bounds
from app.services.hydro_history import APP_HISTORY_START, NASA_POWER_START


def test_calendar_bounds_use_long_range_providers() -> None:
    today = date(2026, 10, 20)
    bounds = calendar_bounds(today, forecast_days=7)
    assert bounds["history_start"] == APP_HISTORY_START.isoformat()
    assert bounds["operational_start"] == APP_HISTORY_START.isoformat()
    assert bounds["labeled_start"] is not None
    assert bounds["history_end"] == today.isoformat()
    assert bounds["select_max"] == "2026-10-27"
    assert bounds["nasa_power_start"] == NASA_POWER_START.isoformat()
    assert bounds["validated_csv_start"] is not None
