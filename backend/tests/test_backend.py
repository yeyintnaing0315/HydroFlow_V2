import asyncio
from datetime import date, datetime, timezone

import joblib
import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import Location, Observation
from app.schemas.api import AlertCreate, ForecastPoint, HistoricalPoint
from app.services import clients, live_features, persistence, prediction, scheduler
from app.services.risk import academic_risk_score


class GoodModel:
    def predict_proba(self, rows) -> np.ndarray:
        return np.array([[0.58, 0.42]])


class FakeResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


class FakeClient:
    def __init__(self, payload: dict):
        self.payload = payload
        self.calls: list[tuple[tuple, dict]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def get(self, *args, **kwargs) -> FakeResponse:
        self.calls.append((args, kwargs))
        return FakeResponse(self.payload)


@pytest.fixture()
def session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as value:
        yield value
    Base.metadata.drop_all(engine)


@pytest.fixture()
def client(session: Session):
    app.dependency_overrides[get_db] = lambda: session
    with TestClient(app) as value:
        yield value
    app.dependency_overrides.clear()


def use_api_days(monkeypatch, days: list[tuple[date, float, float]]) -> None:
    async def fake_observations(latitude: float, longitude: float):
        return days

    monkeypatch.setattr(live_features, "load_observations", fake_observations)


def test_prediction_valid_and_invalid_request(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(prediction, "load_model", lambda: (GoodModel(), {"threshold": 0.4}))
    use_api_days(monkeypatch, [(date(2026, 1, 2), 5.0, 10.0)])
    response = client.post(
        "/predict",
        json={"date": "2026-01-02", "township_id": "bago", "latitude": 1, "longitude": 2},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["flood_probability"] == 0.42
    assert body["predicted_flood"] is True
    assert body["threshold"] == 0.4
    assert body["model_version"] == "baseline-logistic-v2"
    assert body["alert_recorded"] is False
    assert body["evidence_type"] == "model_prediction"
    assert body["probability_status"] == "uncalibrated_academic_score"
    assert client.post("/predict", json={}).status_code == 422


def test_missing_and_invalid_model(client: TestClient, monkeypatch, tmp_path) -> None:
    missing = tmp_path / "missing.joblib"
    monkeypatch.setattr(prediction, "model_path", lambda: missing)
    monkeypatch.setattr(prediction, "metadata_path", lambda: missing)
    prediction.load_model.cache_clear()
    with pytest.raises(prediction.ModelUnavailableError):
        prediction.load_model()
    response = client.post(
        "/predict",
        json={"date": "2026-01-02", "township_id": "bago", "latitude": 1, "longitude": 2},
    )
    assert response.status_code == 503

    invalid = tmp_path / "invalid.joblib"
    joblib.dump({"not": "a model"}, invalid)
    metadata = tmp_path / "metadata.json"
    metadata.write_text('{"threshold": 0.5}', encoding="utf-8")
    monkeypatch.setattr(prediction, "model_path", lambda: invalid)
    monkeypatch.setattr(prediction, "metadata_path", lambda: metadata)
    prediction.load_model.cache_clear()
    with pytest.raises(prediction.ModelUnavailableError, match="predict_proba"):
        prediction.load_model()
    prediction.load_model.cache_clear()


@pytest.mark.parametrize(
    ("precipitation", "discharge", "expected"),
    [(0, 0, "low"), (20, 0, "moderate"), (40, 0, "high"), (60, 0, "severe")],
)
def test_risk_boundaries(precipitation: float, discharge: float, expected: str) -> None:
    score, level = academic_risk_score(precipitation, discharge)
    assert 0 <= score <= 100
    assert level == expected


def test_database_alert_dedupe_and_history_filters(session: Session) -> None:
    location = Location(name="Test", latitude=1, longitude=2)
    session.add(location)
    session.commit()
    issued_at = datetime(2026, 1, 2, tzinfo=timezone.utc)
    alert_data = AlertCreate(
        location_id=location.id, issued_at=issued_at, level="high", message="Test alert"
    )
    first = persistence.add_alert(session, alert_data)
    second = persistence.add_alert(session, alert_data)
    assert first.id == second.id
    assert len(persistence.list_alerts(session, location.id, "high")) == 1

    session.add_all(
        [
            Observation(
                location_id=location.id,
                observed_at=datetime(2026, 1, day, 12, tzinfo=timezone.utc),
                source="test",
                precipitation_mm=float(day),
            )
            for day in (1, 2, 3)
        ]
    )
    session.commit()
    observations = persistence.list_observations(
        session, location.id, date(2026, 1, 2), date(2026, 1, 2)
    )
    assert [item.precipitation_mm for item in observations] == [2.0]


def test_high_risk_prediction_does_not_create_an_official_alert(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(prediction, "load_model", lambda: (GoodModel(), {"threshold": 0.4}))
    use_api_days(monkeypatch, [(date(2026, 1, 2), 60.0, 0.0)])
    payload = {"date": "2026-01-02", "township_id": "bago", "latitude": 17.3, "longitude": 96.4}
    first = client.post("/predict", json=payload)
    second = client.post("/predict", json=payload)
    alerts = client.get("/alerts")

    assert first.status_code == second.status_code == 200
    assert first.json()["alert_recorded"] is False
    assert alerts.status_code == 200
    assert alerts.json() == []


def test_alert_route(client: TestClient, session: Session) -> None:
    location = Location(name="Test", latitude=1, longitude=2)
    session.add(location)
    session.commit()
    persistence.add_alert(
        session,
        AlertCreate(
            location_id=location.id,
            issued_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
            level="moderate",
            message="Academic alert",
        ),
    )
    response = client.get(f"/alerts?location_id={location.id}&level=moderate")
    assert response.status_code == 200
    assert response.json()[0]["message"] == "Academic alert"


def test_operational_mutations_require_configured_admin_key(client, monkeypatch) -> None:
    monkeypatch.delenv("ADMIN_API_KEY", raising=False)
    assert client.post("/runs/prediction").status_code == 503
    monkeypatch.setenv("ADMIN_API_KEY", "test-secret")
    assert client.post("/runs/prediction").status_code == 401
    assert (
        client.post(
            "/official-warnings/import",
            headers={"X-Admin-Key": "wrong-secret"},
            json={},
        ).status_code
        == 401
    )
    invalid = client.post(
        "/official-warnings/import",
        headers={"X-Admin-Key": "test-secret"},
        json={
            "external_id": "dmh-test",
            "issued_at": "2026-10-15T00:00:00Z",
            "severity": "warning",
            "message": "Traceable test warning",
            "source_url": "http://insecure.example",
        },
    )
    assert invalid.status_code == 422


def test_operational_read_endpoints_are_available(client) -> None:
    assert client.get("/sources").status_code == 200
    for path in (
        "/runs",
        "/risk-results",
        "/inundation-products",
        "/settlements",
        "/exposure-summaries",
    ):
        response = client.get(path)
        assert response.status_code == 200
        assert response.json() == []


def test_manual_run_reports_unclaimed_race(client, monkeypatch) -> None:
    async def no_claim(*_args, **_kwargs):
        return None

    monkeypatch.setenv("ADMIN_API_KEY", "test-secret")
    monkeypatch.setattr(scheduler, "execute_prediction_run", no_claim)
    response = client.post(
        "/runs/prediction",
        headers={"X-Admin-Key": "test-secret"},
    )
    assert response.status_code == 409
    assert "not claimed" in response.json()["detail"]


def test_external_routes_are_mocked(client: TestClient, monkeypatch) -> None:
    async def fake_weather(latitude: float, longitude: float):
        return [ForecastPoint(timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc), precipitation_mm=2)]

    async def fake_discharge(latitude: float, longitude: float):
        return [ForecastPoint(timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc), discharge_m3_s=8)]

    captured = {}

    async def fake_history(latitude: float, longitude: float, start: date, end: date):
        captured.update(start=start, end=end)
        return [HistoricalPoint(date=start, precipitation_mm=None, temperature_c=25)]

    monkeypatch.setattr(clients, "open_meteo_forecast", fake_weather)
    monkeypatch.setattr(clients, "glofas_discharge_forecast", fake_discharge)
    monkeypatch.setattr(clients, "nasa_power_history", fake_history)

    forecast = client.get("/forecast?latitude=1&longitude=2")
    assert forecast.status_code == 200
    assert len(forecast.json()["points"]) == 1
    assert forecast.json()["points"][0]["discharge_m3_s"] == 8
    history = client.get(
        "/historical?latitude=1&longitude=2&start=2026-01-02&end=2026-01-03&township_id=bago"
    )
    assert history.status_code == 200
    assert history.json()["points"][0]["temperature_c"] == 25
    assert captured == {"start": date(2026, 1, 2), "end": date(2026, 1, 3)}

    async def failing_history(*_args, **_kwargs):
        raise ValueError("provider down")

    monkeypatch.setattr(clients, "nasa_power_history", failing_history)
    stored = client.get(
        "/historical?latitude=1&longitude=2&start=2026-01-02&end=2026-01-03&township_id=bago"
    )
    assert stored.status_code == 200
    assert stored.json()["points"][0]["date"] == "2026-01-02"


def test_blank_nasa_day_is_filled_from_open_meteo(client: TestClient, monkeypatch) -> None:
    async def blank_history(latitude: float, longitude: float, start: date, end: date):
        return [
            HistoricalPoint(
                date=date(2026, 10, 16),
                precipitation_mm=None,
                temperature_c=None,
                relative_humidity_pct=None,
            )
        ]

    async def recent_weather(latitude: float, longitude: float, past_days: int = 62, forecast_days: int = 7):
        return [
            {
                "date": date(2026, 10, 16),
                "rainfall_mm": 6.5,
                "temperature_c": 27.2,
                "relative_humidity_pct": 89.0,
                "wind_speed_m_s": 1.1,
            }
        ]

    monkeypatch.setattr(clients, "nasa_power_history", blank_history)
    monkeypatch.setattr(clients, "open_meteo_daily_weather", recent_weather)
    response = client.get(
        "/historical?latitude=18.1&longitude=95.6&start=2026-10-12&end=2026-10-16&township_id=paungde"
    )
    assert response.status_code == 200
    point = response.json()["points"][0]
    assert point["date"] == "2026-10-16"
    assert point["precipitation_mm"] == 6.5
    assert point["temperature_c"] == 27.2
    assert point["relative_humidity_pct"] == 89.0
    assert client.get(
        "/historical?latitude=1&longitude=2&start=2026-01-03&end=2026-01-02"
    ).status_code == 422


def test_topography_reads_copernicus_elevation_without_returning_the_key(client, monkeypatch) -> None:
    payload = {
        "Elevation": "18.4",
        "Shortname": "COP30",
        "VCRS_EPSG": "3855",
        "Unit": "Meters",
    }
    created: dict[str, FakeClient] = {}

    def factory(**kwargs):
        created["client"] = FakeClient(payload)
        return created["client"]

    clients._elevation_cache.clear()
    monkeypatch.setenv("OPENTOPOGRAPHY_API_KEY", "test-key")
    monkeypatch.setattr(clients, "_load_project_env", lambda: None)
    monkeypatch.setattr(clients.httpx, "AsyncClient", factory)

    first = client.get("/topography?latitude=17.3358&longitude=96.4839")
    second = client.get("/topography?latitude=17.3358&longitude=96.4839")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["elevation_m"] == 18.4
    assert first.json()["dataset"] == "COP30"
    assert first.json()["vertical_datum"] == "EGM2008"
    assert "test-key" not in first.text
    assert "flood model does not use this value" in first.json()["note"]
    assert len(created["client"].calls) == 1
    requested = created["client"].calls[0][1]["params"]
    assert requested["API_Key"] == "test-key"
    assert requested["dataset"] == "COP30"
    assert requested["latitude"] == 17.3358


def test_topography_reports_a_missing_key(client, monkeypatch) -> None:
    monkeypatch.delenv("OPENTOPOGRAPHY_API_KEY", raising=False)
    monkeypatch.setattr(clients, "_load_project_env", lambda: None)
    response = client.get("/topography?latitude=17.3&longitude=96.4")
    assert response.status_code == 503
    assert response.json()["detail"] == "OPENTOPOGRAPHY_API_KEY is not set"


def test_clients_validate_and_convert_missing_values(monkeypatch) -> None:
    nasa_payload = {
        "properties": {
            "parameter": {
                "PRECTOTCORR": {"20260101": -999},
                "T2M": {"20260101": 23.5},
                "RH2M": {"20260101": -999},
            }
        }
    }
    created: dict[str, FakeClient] = {}

    def factory(**kwargs):
        created["client"] = FakeClient(nasa_payload)
        return created["client"]

    monkeypatch.setattr(clients.httpx, "AsyncClient", factory)
    points = asyncio.run(
        clients.nasa_power_history(1, 2, date(2026, 1, 1), date(2026, 1, 1))
    )
    assert points[0].precipitation_mm is None
    assert points[0].temperature_c == 23.5
    assert points[0].relative_humidity_pct is None
    requested = created["client"].calls[0][1]["params"]
    assert requested["parameters"] == "PRECTOTCORR,T2M,RH2M,WS2M"
    assert requested["time-standard"] == "UTC"

    monkeypatch.setattr(
        clients.httpx, "AsyncClient", lambda **kwargs: FakeClient({"daily": {}})
    )
    with pytest.raises(ValueError, match="GloFAS"):
        asyncio.run(clients.glofas_discharge_forecast(1, 2))
