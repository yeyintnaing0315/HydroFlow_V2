from datetime import date

from app.services.hydro_offline_db import connect, hydrology_error_message, upsert_hydrology_rows


def test_hydrology_error_message_mentions_backfill() -> None:
    message = hydrology_error_message(
        window_start=date(2020, 6, 25),
        window_end=date(2020, 6, 25),
        operational_start=date(2010, 1, 1),
    )
    assert "2010" in message
    assert "backfill" in message.lower()


def test_upsert_and_read_roundtrip(tmp_path, monkeypatch) -> None:
    db = tmp_path / "offline.sqlite"
    monkeypatch.setattr("app.services.hydro_offline_db.DB_PATH", db)
    connect()
    upsert_hydrology_rows(
        [
            (
                "bago",
                "2020-06-25",
                12.0,
                45.0,
                None,
                None,
                None,
                28.0,
                80.0,
                2.0,
                '{"rainfall":"test","discharge":"test"}',
            )
        ]
    )
    from app.services.hydro_offline_db import observations_for_range

    rows = observations_for_range("bago", date(2020, 6, 20), date(2020, 6, 30))
    assert len(rows) == 1
    assert rows[0]["rainfall_mm"] == 12.0
    assert rows[0]["river_discharge_m3s"] == 45.0
