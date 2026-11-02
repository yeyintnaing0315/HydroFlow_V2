from fastapi.testclient import TestClient

from app.main import app


def test_help_summary_returns_bago_archive_row() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/help/summary",
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
    assert body["expected_affected_people"] > 0
    assert body["assistance_priority"] in {"high", "severe"}
