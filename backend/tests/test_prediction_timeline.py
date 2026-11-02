from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import live_features, prediction
from app.services.prediction_timeline import (
    _apply_validated_historical_risk,
    build_timeline,
    date_window,
    period_type_for,
    probability_risk_level,
    score_township_on_date,
)


def _complete_days(start: date, count: int = 36) -> list[dict]:
    return [
        {
            "date": start + timedelta(days=offset),
            "rainfall_mm": 12.0 + offset,
            "river_discharge_m3s": 180.0 + offset,
            "temperature_c": 27.5,
            "relative_humidity_pct": 82.0,
            "wind_speed_m_s": 1.4,
            "rainfall_source": "Open-Meteo forecast/reanalysis",
            "meteorology_source": "NASA POWER",
            "discharge_source": "Open-Meteo Flood API modeled GloFAS-derived discharge",
            "in_training_set": True,
        }
        for offset in range(count)
    ]


def test_prediction_timeline_route_accepts_archive_reference_evidence(monkeypatch) -> None:
    as_of = date(2023, 8, 10)
    start, _ = date_window(as_of)

    async def fake_observations(
        _township_id: str,
        _latitude: float,
        _longitude: float,
        _start: date,
        _end: date,
        **_,
    ):
        return _complete_days(start - timedelta(days=live_features.CONTEXT_DAYS), 90)

    monkeypatch.setattr(live_features, "observations_for_timeline", fake_observations)
    prediction.load_model.cache_clear()
    with TestClient(app) as client:
        response = client.post(
            "/prediction/timeline",
            json={
                "date": "2023-08-08",
                "as_of": "2023-08-08",
                "township_id": "bago",
                "township_name_en": "Bago",
                "latitude": 17.335,
                "longitude": 96.481,
            },
        )
    assert response.status_code == 200, response.text
    body = response.json()
    archive_days = [day for day in body["days"] if day["evidence_type"] == "archive_reference"]
    assert archive_days, "expected at least one archive_reference day in timeline"


def test_apply_validated_historical_risk_elevates_display() -> None:
    day = {
        "period_type": "historical",
        "impact_level": "severe",
        "probability_risk_level": "low",
        "risk_level": "low",
        "key_factors": [],
    }
    updated = _apply_validated_historical_risk(day)
    assert updated["probability_risk_level"] == "severe"
    assert updated["risk_level"] == "severe"
    assert any("Validated historical impact" in factor for factor in updated["key_factors"])


def test_probability_risk_level_bands() -> None:
    assert probability_risk_level(0.1) == "low"
    assert probability_risk_level(0.3) == "moderate"
    assert probability_risk_level(0.6) == "high"
    assert probability_risk_level(0.9) == "severe"
    assert probability_risk_level(None) is None


def test_date_window_and_period_type() -> None:
    as_of = date(2026, 10, 10)
    start, end = date_window(as_of)
    assert (end - start).days == 14
    assert period_type_for(date(2026, 10, 9), as_of) == "historical"
    assert period_type_for(as_of, as_of) == "current"
    assert period_type_for(date(2026, 10, 11), as_of) == "forecast"


@pytest.mark.asyncio
async def test_build_timeline_window_and_period_types(monkeypatch) -> None:
    as_of = date(2026, 10, 10)
    start, _ = date_window(as_of)

    async def fake_observations(
        _township_id: str,
        _latitude: float,
        _longitude: float,
        _start: date,
        _end: date,
        **_,
    ):
        # Model rows need ~30 prior days for rolling rainfall / discharge features.
        return _complete_days(start - timedelta(days=live_features.CONTEXT_DAYS), 90)

    monkeypatch.setattr(live_features, "observations_for_timeline", fake_observations)
    prediction.load_model.cache_clear()
    payload = await build_timeline("bago", 17.336, 96.481, as_of, township_name_en="Bago")

    assert payload["as_of"] == as_of
    assert len(payload["days"]) == 15
    periods = {day["period_type"] for day in payload["days"]}
    assert periods == {"historical", "current", "forecast"}
    current = next(day for day in payload["days"] if day["date"] == as_of)
    assert current["period_type"] == "current"
    assert current["evidence_type"] == "model_prediction"
    assert 0 <= current["flood_probability"] <= 1
    assert current["probability_risk_level"] in {"low", "moderate", "high", "severe"}


@pytest.mark.asyncio
async def test_build_timeline_marks_validated_severe_historical_day(monkeypatch) -> None:
    as_of = date(2023, 8, 10)
    start, _ = date_window(as_of)

    async def fake_observations(
        _township_id: str,
        _latitude: float,
        _longitude: float,
        _start: date,
        _end: date,
        **_,
    ):
        return _complete_days(start - timedelta(days=live_features.CONTEXT_DAYS), 90)

    monkeypatch.setattr(live_features, "observations_for_timeline", fake_observations)
    prediction.load_model.cache_clear()
    payload = await build_timeline(
        "bago",
        17.336,
        96.481,
        as_of,
        township_name_en="Bago",
        relief_slug="bago",
    )
    severe_day = next(day for day in payload["days"] if day["date"] == date(2023, 8, 8))
    assert severe_day["period_type"] == "historical"
    assert severe_day["observed_flood"] is True
    assert severe_day["impact_level"] == "severe"
    assert severe_day["probability_risk_level"] in {"low", "moderate", "high", "severe"}
    assert severe_day["flood_probability"] is not None


@pytest.mark.asyncio
async def test_map_score_dedupes_observation_loads(monkeypatch) -> None:
    calls = {"count": 0}
    target = date(2026, 10, 10)

    async def fake_observations(
        _township_id: str,
        _latitude: float,
        _longitude: float,
        _start: date,
        _end: date,
        **_,
    ):
        calls["count"] += 1
        return _complete_days(target - timedelta(days=live_features.CONTEXT_DAYS), 90)

    monkeypatch.setattr(live_features, "observations_for_timeline", fake_observations)
    prediction.load_model.cache_clear()

    class FakeArea:
        source_code = "a"
        name_en = "A"
        centroid_latitude = 17.33
        centroid_longitude = 96.48
        parent_id = 1

    class FakeArea2:
        source_code = "a"
        name_en = "B"
        centroid_latitude = 17.33
        centroid_longitude = 96.48
        parent_id = 1

    cache: dict = {}
    await score_township_on_date(FakeArea(), target, cache, "a")
    await score_township_on_date(FakeArea2(), target, cache, "a")
    assert calls["count"] == 1
