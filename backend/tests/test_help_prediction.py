from datetime import date

from fastapi.testclient import TestClient

from app.main import app
from app.services import live_features
from app.services.help_prediction import load_help_model


def test_saved_help_model_serves_assistance_outlook(monkeypatch) -> None:
    async def fake_observations(latitude: float, longitude: float):
        return [(date(2026, 10, 1), 25.0, 250.0), (date(2026, 10, 2), 10.0, 200.0)]

    monkeypatch.setattr(live_features, "load_observations", fake_observations)
    load_help_model.cache_clear()
    with TestClient(app) as client:
        response = client.post(
            "/help",
            json={
                "date": "2026-10-01",
                "township_id": "bago",
                "latitude": 17.336,
                "longitude": 96.481,
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["model_version"].startswith("flood-help")
    assert body["disclaimer"] == "Academic planning aid. Not an operational humanitarian response plan."
    assert [day["date"] for day in body["days"]] == ["2026-10-01", "2026-10-02"]
    for day in body["days"]:
        assert 0 <= day["help_probability"] <= 1
        assert day["expected_affected_people"] >= 0
        assert day["expected_households"] >= 0
        assert day["shelter_kits"] == day["expected_households"]
        assert day["food_rations_3d"] == day["expected_affected_people"] * 3
        assert day["drinking_water_liters_3d"] == day["expected_affected_people"] * 45
        assert day["assistance_priority"] in {"none", "low", "moderate", "high", "severe"}
