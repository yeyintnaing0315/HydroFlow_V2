from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "hydroflow-api"
    assert body["version"] == "0.1.0"
    assert set(body["models"]) == {"flood", "help", "allocation"}
    assert all(isinstance(value, bool) for value in body["models"].values())
