from datetime import date

from app.schemas.api import FloodCaseItem
from app.services import flood_cases


def test_collapse_consecutive_recorded_days():
    rows = [
        FloodCaseItem(
            place="Bago",
            township_id="bago",
            depot="Bago (east)",
            source="recorded",
            level="severe",
            start_date=date(2023, 8, 8),
            end_date=date(2023, 8, 8),
            peak_date=date(2023, 8, 8),
            peak_score=8385.4,
            households=4521,
            affected_people=19322,
            days=1,
        ),
        FloodCaseItem(
            place="Bago",
            township_id="bago",
            depot="Bago (east)",
            source="recorded",
            level="severe",
            start_date=date(2023, 8, 9),
            end_date=date(2023, 8, 9),
            peak_date=date(2023, 8, 9),
            peak_score=8385.4,
            households=4521,
            affected_people=19322,
            days=1,
        ),
    ]
    merged = flood_cases._collapse_events(rows)
    assert len(merged) == 1
    assert merged[0].start_date == date(2023, 8, 8)
    assert merged[0].end_date == date(2023, 8, 9)
    assert merged[0].days == 2
