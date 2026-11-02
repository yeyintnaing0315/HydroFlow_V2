from datetime import date

from app.services import live_features
from app.services.help_prediction import predict_help_from_flood_and_inventory


def test_archive_fallback_uses_recorded_impacts_for_known_flood_day() -> None:
    scored = predict_help_from_flood_and_inventory(
        {"rainfall_mm": 10.0, "river_discharge_m3s": 5.0},
        planning_date=date(2023, 8, 8),
        township_name_en="Bago",
        township_id="bago",
    )
    assert scored["expected_affected_people"] > 0
    assert scored["assistance_priority"] in {"high", "severe"}
    assert scored["model_version"] == "flood-help-topredict-workbook"


def test_help_endpoint_works_without_saved_artifact(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from app.main import app
    from app.services import help_prediction

    async def fake_observations(latitude: float, longitude: float):
        return [(date(2023, 8, 8), 39.4, 5.8)]

    monkeypatch.setattr(live_features, "load_observations", fake_observations)
    monkeypatch.setattr(help_prediction, "help_model_available", lambda: False)

    with TestClient(app) as client:
        response = client.post(
            "/help",
            json={
                "date": "2023-08-08",
                "township_id": "bago",
                "township_name_en": "Bago",
                "latitude": 17.336,
                "longitude": 96.481,
            },
        )

    assert response.status_code == 200
    body = response.json()
    day = body["days"][0]
    assert day["expected_affected_people"] > 0
    assert day["assistance_priority"] in {"high", "severe"}
