from datetime import date

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import flood_history


@pytest.fixture()
def history_file(tmp_path, monkeypatch):
    frame = pd.DataFrame(
        [
            ["2024-08-02", "bago", "Bago", 17.3, 96.4, 100, 500, 1],
            ["2024-08-01", "pyay", "Pyay", 18.8, 95.2, None, None, 1],
            ["2024-08-01", "bago", "Bago", 17.3, 96.4, 10, 0, 0],
        ],
        columns=[
            "date",
            "township_id",
            "township",
            "lat",
            "lng",
            "households",
            "affected_people",
            "flood",
        ],
    )
    path = tmp_path / "validated_daily.csv"
    frame.to_csv(path, index=False)
    monkeypatch.setattr(flood_history, "history_path", lambda: path)
    flood_history._flood_days.cache_clear()
    flood_history.list_townships.cache_clear()
    yield
    flood_history._flood_days.cache_clear()
    flood_history.list_townships.cache_clear()


def test_recorded_floods_filter_impacts_and_ignore_non_flood_days(history_file) -> None:
    matched, records = flood_history.recorded_floods(township_id="bago")

    assert matched == 1
    assert records[0].date == date(2024, 8, 2)
    assert records[0].impact_severity == "moderate"
    assert records[0].households == 100


def test_assistance_brief_ranks_recorded_impacts(history_file) -> None:
    brief = flood_history.assistance_brief()

    assert brief["recorded_flood_days"] == 2
    assert brief["recorded_households"] == 100
    assert brief["recorded_affected_people"] == 500
    assert brief["townships_with_impact"] == 1
    assert brief["highest_impacts"][0].township_id == "bago"
    assert brief["highest_impacts"][0].impact_severity == "moderate"


def test_help_brief_route(history_file) -> None:
    with TestClient(app) as client:
        response = client.get("/help-brief")

    assert response.status_code == 200
    body = response.json()
    assert body["recorded_affected_people"] == 500
    assert body["disclaimer"] == "Recorded impacts, not flood-help model predictions."
    assert body["highest_impacts"][0]["township"] == "Bago"


def test_flood_history_route(history_file) -> None:
    with TestClient(app) as client:
        response = client.get("/flood-history?township_id=pyay")

    assert response.status_code == 200
    body = response.json()
    assert body["matched_records"] == 1
    assert body["records"][0]["impact_severity"] == "none"
    assert body["disclaimer"] == "Recorded impacts, not model predictions."
    assert client.get("/flood-history?start=2024-08-02&end=2024-08-01").status_code == 422
