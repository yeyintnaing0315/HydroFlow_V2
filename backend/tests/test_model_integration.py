from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.services import live_features
from app.services.prediction import load_model, model_version_name


def _complete_days(start: date, count: int = 36) -> list[dict]:
    return [
        {
            "date": start + timedelta(days=offset),
            "rainfall_mm": 12.0 + offset,
            "river_discharge_m3s": 180.0 + offset,
            "temperature_c": 27.5,
            "relative_humidity_pct": 82.0,
            "wind_speed_m_s": 1.4,
            "soil_moisture_0_to_7cm": 0.35,
            "soil_moisture_7_to_28cm": 0.38,
            "et0_fao_evapotranspiration": 3.1,
            "rainfall_source": "Open-Meteo forecast/reanalysis",
            "meteorology_source": "NASA POWER",
            "discharge_source": "Open-Meteo Flood API modeled GloFAS-derived discharge",
            "in_training_set": True,
        }
        for offset in range(count)
    ]


def test_saved_model_serves_probability(monkeypatch) -> None:
    start = date(2026, 9, 1)

    async def fake_observations(latitude: float, longitude: float):
        return _complete_days(start)

    monkeypatch.setattr(live_features, "load_observations", fake_observations)
    load_model.cache_clear()
    _, metadata = load_model()
    with TestClient(app) as client:
        response = client.post(
            "/outlook",
            json={
                "date": "2026-10-01",
                "township_id": "bago",
                "latitude": 17.336,
                "longitude": 96.481,
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "Open-Meteo rainfall, NASA POWER meteorology, and GloFAS discharge"
    assert body["model_version"] == model_version_name(metadata)
    assert body["in_training_set"] is True
    assert [day["date"] for day in body["days"]][:2] == ["2026-10-01", "2026-10-02"]
    assert all(0 <= day["flood_probability"] <= 1 for day in body["days"])
    assert all(day["evidence_type"] == "model_prediction" for day in body["days"])
    assert all(
        day["probability_status"] == "uncalibrated_academic_score"
        for day in body["days"]
    )
    assert all(day["forecast_horizon_hours"] >= 0 for day in body["days"])
    assert all(day["temperature_c"] == 27.5 for day in body["days"])
    assert all("retrieved_at" in day["input_freshness"] for day in body["days"])
    assert all("meteorology" in day["input_freshness"] for day in body["days"])
    assert all("next 3 days" in day["uncertainty"] or "out-of-sample" in day["uncertainty"] for day in body["days"])


def test_nearest_river_cell_snaps_bago_centroid() -> None:
    cell = live_features.nearest_river_cell(17.33583, 96.48389)
    assert cell is not None
    assert cell["township"] == "Bago"
    assert cell["in_training_set"] is True
    assert cell["river_latitude"] == 17.32501
