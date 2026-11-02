from datetime import date

import pytest
from sqlalchemy import select

from app.models import FloodLabel
from app.services import live_features
from app.services.copernicus_glofas import fetch_gfm_water_fraction, remember_observed_gfm
from app.services.forecast_store import import_flood_labels
from app.services.risk import horizon_probability


def test_horizon_is_one_minus_the_product_of_daily_survival():
    assert horizon_probability([0.2, 0.5, 0.0, 0.1]) == pytest.approx(1 - (0.8 * 0.5 * 1.0 * 0.9))
    assert horizon_probability([None, None]) is None
    assert horizon_probability([0.25, None]) == pytest.approx(0.25)


def test_import_keeps_only_observed_relief_flood_days(session, tmp_path, monkeypatch):
    csv_path = tmp_path / "validated_daily.csv"
    csv_path.write_text(
        "date,township_id,township,affected_people,flood\n"
        "2021-05-01,bago,Bago,12,1\n"
        "2005-01-01,bago,Bago,0,0\n"
        "2010-06-01,pyay,Pyay,,0\n",
        encoding="utf-8",
    )
    module = live_features._static_prior()
    monkeypatch.setattr(module, "discover_label_path", lambda: csv_path)
    import_flood_labels(
        session,
        [{"id": "bago", "name_en": "Bago"}, {"id": "pyay", "name_en": "Pyay"}],
    )
    session.flush()
    rows = session.scalars(select(FloodLabel)).all()
    assert [(row.township_id, row.observed_date.isoformat(), row.observed) for row in rows] == [
        ("bago", "2021-05-01", True)
    ]


def test_gfm_without_a_token_does_not_call_the_api(monkeypatch):
    monkeypatch.setattr("app.services.copernicus_glofas._load_env", lambda: None)
    monkeypatch.delenv("COPERNICUS_GFM_TOKEN", raising=False)

    def refuse(*_args, **_kwargs):
        raise AssertionError("GFM was called without a token")

    monkeypatch.setattr("urllib.request.urlopen", refuse)
    assert fetch_gfm_water_fraction(17.3, 96.4, date(2024, 8, 1)) is None
    remember_observed_gfm("bago", 17.3, 96.4, date(2024, 8, 1))


def test_gfm_dry_scene_is_not_stored(monkeypatch):
    monkeypatch.setattr("app.services.copernicus_glofas._load_env", lambda: None)
    monkeypatch.setenv("COPERNICUS_GFM_TOKEN", "token")

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"water_fraction": 0.0}'

    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: Response())
    assert fetch_gfm_water_fraction(17.3, 96.4, date(2024, 8, 1)) is None
