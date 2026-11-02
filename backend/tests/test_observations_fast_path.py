from datetime import date, timedelta

import pytest

from app.services import live_features


@pytest.mark.asyncio
async def test_historical_timeline_uses_catalog_without_reanalysis(monkeypatch) -> None:
    calls = {"reanalysis": 0}

    async def fail_reanalysis(*_args, **_kwargs):
        calls["reanalysis"] += 1
        raise AssertionError("reanalysis should not run when catalog covers the window")

    monkeypatch.setattr(live_features, "_fetch_reanalysis_window", fail_reanalysis)
    window_start = date(2023, 8, 1)
    window_end = date(2023, 8, 14)
    rows = await live_features.observations_for_timeline(
        "bago",
        17.335,
        96.481,
        window_start,
        window_end,
        catalog_township_id="bago",
    )
    assert calls["reanalysis"] == 0
    assert rows
    context_start = window_start - timedelta(days=live_features.CONTEXT_DAYS)
    assert min(row["date"] for row in rows) <= context_start


@pytest.mark.asyncio
async def test_future_window_persists_local_hydrology_without_providers(monkeypatch) -> None:
    async def fail(*_args, **_kwargs):
        raise AssertionError("external hydrology should not run when local rows cover the window")

    monkeypatch.setattr(live_features, "_supplement_from_providers", fail)
    monkeypatch.setattr(live_features, "_fetch_reanalysis_window", fail)
    monkeypatch.setattr(live_features, "load_observations", fail)
    live_features._observations_cache.clear()
    window_start = date(2026, 10, 20)
    window_end = date(2026, 10, 30)
    rows = await live_features.observations_for_timeline(
        "kyauktaga",
        18.21,
        96.61,
        window_start,
        window_end,
        catalog_township_id="kyauktaga",
    )
    target = date(2026, 10, 27)
    match = next(row for row in rows if row["date"] == target)
    assert match["rainfall_mm"] is not None
    assert match["river_discharge_m3s"] is not None
    feature_rows = live_features.features_on_or_after(
        rows,
        window_start - timedelta(days=live_features.CONTEXT_DAYS),
        "kyauktaga",
        18.21,
        96.61,
    )
    scored = next(row for row in feature_rows if row["date"] == target)
    assert live_features.row_has_model_features(scored, live_features.NEW_MODEL_FEATURES)
