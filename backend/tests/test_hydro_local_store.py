from datetime import date
from pathlib import Path

import pandas as pd

from app.services import hydro_local_store
from app.services.hydro_sources import GLOFAS_DISCHARGE_DIR, HYDRO_MERGED_DIR, OPEN_METEO_ARCHIVE_DIR


def test_local_observations_from_merged_csv(tmp_path: Path, monkeypatch) -> None:
    merged = tmp_path / "hydro_merged"
    merged.mkdir()
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(["2020-06-01", "2020-06-02"]),
            "rainfall_mm": [10.0, 12.0],
            "river_discharge_m3s": [100.0, 110.0],
            "temperature_c": [28.0, 29.0],
            "relative_humidity_pct": [80.0, 81.0],
            "wind_speed_m_s": [1.5, 1.6],
        }
    )
    frame.to_csv(merged / "bago.csv", index=False)

    monkeypatch.setattr(hydro_local_store, "HYDRO_MERGED_DIR", merged)
    monkeypatch.setattr(hydro_local_store, "OPEN_METEO_ARCHIVE_DIR", tmp_path / "om")
    monkeypatch.setattr(hydro_local_store, "GLOFAS_DISCHARGE_DIR", tmp_path / "gf")
    monkeypatch.setattr(hydro_local_store, "NASA_POWER_HYDRO_DIR", tmp_path / "np")

    rows = hydro_local_store.local_observations_for_range(
        "bago", date(2020, 6, 1), date(2020, 6, 2)
    )
    assert len(rows) == 2
    assert rows[0]["rainfall_mm"] == 10.0
    assert rows[0]["discharge_source"] == "local glofas_discharge"
