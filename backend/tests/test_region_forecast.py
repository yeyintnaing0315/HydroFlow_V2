"""Persisted region forecasts and the river-distance prior."""

from __future__ import annotations

import asyncio
import time
from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import FloodLabel, PredictionRun, TownshipForecast, TownshipStaticFeatures
from app.services import live_features
from app.services import forecast_store
from app.services.forecast_store import early_warning_reason
from app.services.risk import band_to_risk_level, flood_probability_band


def test_local_hydro_ids_cover_western_townships() -> None:
    from app.services.hydro_sources import merged_series_path
    from app.services.live_features import storage_ids_for

    for name in (
        "bago",
        "pyay",
        "letpadan",
        "nattalin",
        "padaung",
        "paukkaung",
        "okpo",
        "gyobingauk",
        "paungde",
        "shwedaung",
    ):
        stored = storage_ids_for(name)
        assert any(merged_series_path(item).is_file() for item in stored), (name, stored)
    assert "MMR007001701" in storage_ids_for("bago")


def test_flood_bands_and_early_warning() -> None:
    assert flood_probability_band(0.0) == "low"
    assert flood_probability_band(0.24) == "low"
    assert flood_probability_band(0.25) == "moderate"
    assert flood_probability_band(0.49) == "moderate"
    assert flood_probability_band(0.50) == "high"
    assert flood_probability_band(0.74) == "high"
    assert flood_probability_band(0.75) == "very_high"
    assert band_to_risk_level("very_high") == "severe"

    raised, reason, level = early_warning_reason(
        ["low", "moderate", "high", "very_high"],
        [10.0, 10.0, 10.0, 10.0],
        None,
    )
    assert raised is True
    assert level == "severe"
    assert reason is not None and "rises into high" in reason

    discharge_only, discharge_reason, discharge_level = early_warning_reason(
        ["low", "low", "low", "low"],
        [1.0, 40.0, 1.0, 1.0],
        12.0,
    )
    assert discharge_only is True
    assert discharge_level == "high"
    assert discharge_reason is not None and "95th percentile" in discharge_reason

    quiet, quiet_reason, quiet_level = early_warning_reason(
        ["low", "moderate", "low", "moderate"],
        [1.0, 1.0, 1.0, 1.0],
        12.0,
    )
    assert quiet is False
    assert quiet_reason is None
    assert quiet_level is None


def test_upstream_rainfall_falls_back_without_a_western_river_proxy() -> None:
    module = live_features._static_prior()
    rivers = module.load_river_points(live_features.RIVER_POINTS_CSV)
    assert rivers
    western = module.upstream_spec(18.82, 95.22, rivers)
    assert western["mode"] == "centroid_only_fallback"
    assert "centroid" in western["note"]
    eastern = module.upstream_spec(17.33, 96.48, rivers)
    assert eastern["mode"] == "upstream_river_proxy"
    assert eastern["points"]
    missing = module.missing_raster_inputs()
    assert "JRC global river flood hazard v2.1" in missing
    assert "HydroBASINS" in missing


def test_region_forecast_persists_three_day_outlook(client: TestClient, session: Session, monkeypatch) -> None:
    as_of = date(2026, 10, 27)

    async def fake_observations(
        _township_id: str,
        _latitude: float,
        _longitude: float,
        window_start: date,
        window_end: date,
        **_kwargs,
    ):
        rows = []
        day = window_start
        while day <= window_end:
            rows.append(
                {
                    "date": day,
                    "rainfall_mm": 12.0,
                    "river_discharge_m3s": 80.0,
                    "temperature_c": 28.0,
                    "relative_humidity_pct": 80.0,
                    "wind_speed_m_s": 1.5,
                    "rainfall_source": "test",
                    "meteorology_source": "test",
                    "discharge_source": "test",
                    "in_training_set": True,
                }
            )
            day += timedelta(days=1)
        return rows

    async def fake_upstream(_points):
        return {}

    monkeypatch.setattr(live_features, "observations_for_timeline", fake_observations)
    monkeypatch.setattr(live_features, "fetch_upstream_mean", fake_upstream)

    response = client.get("/prediction/region-forecast", params={"as_of": as_of.isoformat()})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["cached"] is False
    assert body["as_of"] == as_of.isoformat()
    assert "academic" in body["disclaimer"].lower()
    assert len(body["scores"]) == 28 * 4
    leads = {score["lead_days"] for score in body["scores"]}
    assert leads == {0, 1, 2, 3}
    scored = [score for score in body["scores"] if score["data_status"] == "model_estimate"]
    assert scored
    assert all(0.0 <= score["flood_probability"] <= 1.0 for score in scored)
    assert all(score["risk_band"] in {"low", "moderate", "high", "very_high"} for score in scored)
    sample = scored[0]
    assert set(sample["drivers"]) == {"rain", "discharge", "floodplain_or_river_distance"}
    assert "JRC global river flood hazard v2.1" in body["missing_inputs"]

    static_count = session.scalar(select(func.count()).select_from(TownshipStaticFeatures))
    assert static_count == 28
    run_count = session.scalar(select(func.count()).select_from(PredictionRun))
    assert run_count == 1
    forecast_count = session.scalar(select(func.count()).select_from(TownshipForecast))
    assert forecast_count == 28 * 4

    again = client.get("/prediction/region-forecast", params={"as_of": as_of.isoformat(), "lead_days": 2})
    assert again.status_code == 200, again.text
    cached = again.json()
    assert cached["cached"] is True
    assert cached["run_id"] == body["run_id"]
    assert {score["lead_days"] for score in cached["scores"]} == {2}
    assert len(cached["scores"]) == 28

    if body["labels_found"]:
        labels = session.scalar(select(func.count()).select_from(FloodLabel))
        assert labels and labels > 0


def test_region_forecast_does_not_call_upstream_open_meteo(
    client: TestClient, session: Session, monkeypatch
) -> None:
    del session

    async def fail_upstream(_points):
        raise AssertionError("region forecast must not call upstream Open-Meteo")

    async def fake_observations(*_args, **_kwargs):
        return []

    monkeypatch.setattr(live_features, "fetch_upstream_mean", fail_upstream)
    monkeypatch.setattr(live_features, "observations_for_timeline", fake_observations)
    response = client.get("/prediction/region-forecast", params={"as_of": "2026-10-27"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["scores"]
    assert {score["data_status"] for score in body["scores"]} <= {"unavailable", "model_estimate"}


def test_region_forecast_returns_when_observation_loading_hangs(
    client: TestClient, session: Session, monkeypatch
) -> None:
    del session

    async def hang(*_args, **_kwargs):
        await asyncio.sleep(30)
        return []

    monkeypatch.setattr(live_features, "observations_for_timeline", hang)
    monkeypatch.setattr(forecast_store, "REQUEST_BUDGET_SECONDS", 0.6)
    started = time.perf_counter()
    response = client.get("/prediction/region-forecast", params={"as_of": "2026-11-02"})
    elapsed = time.perf_counter() - started
    # Local files are scored even when the provider hangs. The bound stays under
    # one 30-second provider wait, so a cancelled budget cannot turn into a stall.
    assert elapsed < 25, elapsed
    assert response.status_code == 200, response.text
    assert response.json()["scores"]
