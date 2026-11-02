"""Print high/severe events and forecast high/severe townships."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.flood_cases import load_catalog  # noqa: E402


def main() -> None:
    catalog = load_catalog(view="events", limit=500)
    print("CATALOG_EVENTS", catalog.counts.model_dump())
    for event in catalog.events:
        if event.start_date == event.end_date:
            dates = event.start_date.isoformat()
        else:
            dates = f"{event.start_date} .. {event.end_date}"
        people = event.affected_people if event.affected_people is not None else "-"
        print(
            f"{event.level}\t{dates}\t{event.place}\t{event.township_id}\t"
            f"{event.source}\t{people}\t{event.depot}"
        )


if __name__ == "__main__":
    main()
