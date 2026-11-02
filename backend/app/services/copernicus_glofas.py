"""CEMS GloFAS historical and ensemble forecast via Copernicus CDS/EWDS."""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _load_env() -> None:
    path = PROJECT_ROOT / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, value = stripped.split("=", 1)
        name = name.strip()
        value = value.strip().strip('"').strip("'")
        if name and name not in os.environ:
            os.environ[name] = value


def cds_configured() -> bool:
    _load_env()
    return bool(os.getenv("CDSAPI_KEY", "").strip() or os.getenv("CDSAPI_URL", "").strip())


def _cds_retrieve(dataset: str, request: dict[str, Any], target: Path) -> bool:
    """Best-effort CDS retrieve; returns False when cdsapi is missing or auth fails."""
    _load_env()
    key = os.getenv("CDSAPI_KEY", "").strip()
    if not key:
        return False
    try:
        import cdsapi  # type: ignore
    except ImportError:
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    client = cdsapi.Client(url=os.getenv("CDSAPI_URL") or None, key=key)
    client.retrieve(dataset, request, str(target))
    return target.is_file()


def fetch_historical_point_series(
    latitude: float,
    longitude: float,
    start: date,
    end: date,
    *,
    cache_dir: Path | None = None,
) -> list[dict[str, Any]]:
    """Return daily discharge, soil moisture, and runoff when CDS extract exists."""
    folder = cache_dir or (PROJECT_ROOT / "data" / "external" / "cems_glofas" / "points")
    key = f"{round(latitude, 3)}_{round(longitude, 3)}"
    cache = folder / f"{key}_{start.isoformat()}_{end.isoformat()}.json"
    if cache.is_file():
        return json.loads(cache.read_text(encoding="utf-8"))
    if not cds_configured():
        return []
    area = [
        round(latitude + 0.05, 3),
        round(longitude - 0.05, 3),
        round(latitude - 0.05, 3),
        round(longitude + 0.05, 3),
    ]
    nc_path = folder / f"{key}_{start.isoformat()}_{end.isoformat()}.nc"
    ok = _cds_retrieve(
        "cems-glofas-historical",
        {
            "system_version": "version_4_0",
            "hydrological_model": "lisflood",
            "product_type": "consolidated",
            "variable": ["river_discharge", "volumetric_soil_water_layer_1", "runoff"],
            "hyear": [str(year) for year in range(start.year, end.year + 1)],
            "hmonth": [f"{month:02d}" for month in range(1, 13)],
            "hday": [f"{day:02d}" for day in range(1, 32)],
            "area": area,
            "format": "netcdf",
        },
        nc_path,
    )
    if not ok:
        return []
    try:
        import xarray as xr  # type: ignore

        dataset = xr.open_dataset(nc_path)
        rows: list[dict[str, Any]] = []
        time_coord = dataset.coords.get("time") or dataset.coords.get("valid_time")
        if time_coord is None:
            return []
        for stamp in time_coord.values:
            day = date.fromisoformat(str(stamp)[:10])
            if day < start or day > end:
                continue
            point = dataset.sel(latitude=latitude, longitude=longitude, method="nearest")
            rows.append(
                {
                    "date": day.isoformat(),
                    "discharge_m3_s": float(point["river_discharge"].values.item())
                    if "river_discharge" in point
                    else None,
                    "soil_moisture": float(point["volumetric_soil_water_layer_1"].values.item())
                    if "volumetric_soil_water_layer_1" in point
                    else None,
                    "runoff": float(point["runoff"].values.item()) if "runoff" in point else None,
                }
            )
        cache.write_text(json.dumps(rows), encoding="utf-8")
        return rows
    except Exception:
        return []


def fetch_ensemble_forecast(
    latitude: float,
    longitude: float,
    *,
    horizon_days: int = 30,
    cache_dir: Path | None = None,
) -> list[dict[str, Any]]:
    """30-day GloFAS ensemble when EWDS/CDS credentials and parser are available."""
    folder = cache_dir or (PROJECT_ROOT / "data" / "external" / "cems_glofas" / "forecast")
    key = f"{round(latitude, 3)}_{round(longitude, 3)}"
    cache = folder / f"{key}_d{horizon_days}.json"
    if cache.is_file():
        return json.loads(cache.read_text(encoding="utf-8"))
    token = os.getenv("COPERNICUS_EWDS_URL", "").strip()
    if token:
        try:
            query = urllib.parse.urlencode(
                {
                    "latitude": latitude,
                    "longitude": longitude,
                    "horizon": horizon_days,
                }
            )
            with urllib.request.urlopen(f"{token.rstrip('/')}/glofas/forecast?{query}", timeout=60) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if isinstance(payload, list):
                cache.write_text(json.dumps(payload), encoding="utf-8")
                return payload
        except Exception:
            pass
    if not cds_configured():
        return []
    today = date.today()
    end = today + timedelta(days=horizon_days)
    nc_path = folder / f"{key}_{today.isoformat()}_{end.isoformat()}.nc"
    area = [
        round(latitude + 0.05, 3),
        round(longitude - 0.05, 3),
        round(latitude - 0.05, 3),
        round(longitude + 0.05, 3),
    ]
    ok = _cds_retrieve(
        "cems-glofas-forecast",
        {
            "system_version": "version_4_0",
            "hydrological_model": "lisflood",
            "product_type": "ensemble_perturbed_forecasts",
            "variable": ["river_discharge"],
            "year": [str(today.year)],
            "month": [f"{today.month:02d}"],
            "day": [f"{today.day:02d}"],
            "leadtime_hour": [str(hour) for hour in range(24, 24 * horizon_days + 1, 24)],
            "area": area,
            "format": "netcdf",
        },
        nc_path,
    )
    if not ok:
        return []
    try:
        import xarray as xr  # type: ignore

        dataset = xr.open_dataset(nc_path)
        rows: list[dict[str, Any]] = []
        for lead in range(1, horizon_days + 1):
            target = today + timedelta(days=lead)
            point = dataset.sel(latitude=latitude, longitude=longitude, method="nearest")
            discharge = float(point["river_discharge"].isel(step=lead - 1).values.item())
            rows.append(
                {
                    "target_date": target.isoformat(),
                    "lead_days": lead,
                    "discharge_m3_s": discharge,
                    "source": "cems-glofas-ensemble",
                }
            )
        cache.write_text(json.dumps(rows), encoding="utf-8")
        return rows
    except Exception:
        return []


def gfm_token_configured() -> bool:
    _load_env()
    return bool(os.getenv("COPERNICUS_GFM_TOKEN", "").strip())


def remember_observed_gfm(
    township_id: str,
    latitude: float,
    longitude: float,
    day: date,
) -> None:
    """Ask GFM for one day. No token means no request. Dry scenes are not stored."""
    if not gfm_token_configured():
        return
    observed = fetch_gfm_water_fraction(latitude, longitude, day)
    if observed is None or observed.get("status") != "observed":
        return
    from app.services.hydro_offline_db import save_observed_gfm

    save_observed_gfm(
        township_id,
        day,
        float(observed["water_fraction"]),
        None if observed.get("detail") is None else str(observed["detail"]),
    )


def fetch_gfm_water_fraction(
    latitude: float,
    longitude: float,
    day: date,
) -> dict[str, Any] | None:
    """Copernicus GFM REST lookup for a single day (validation only)."""
    _load_env()
    token = os.getenv("COPERNICUS_GFM_TOKEN", "").strip()
    if not token:
        return None
    base = os.getenv("COPERNICUS_GFM_URL", "https://global-flood.emergency.copernicus.eu/api/v1").rstrip("/")
    query = urllib.parse.urlencode(
        {
            "lat": latitude,
            "lon": longitude,
            "date": day.isoformat(),
        }
    )
    try:
        request = urllib.request.Request(
            f"{base}/water?{query}",
            headers={"Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(request, timeout=45) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None
    fraction = payload.get("water_fraction") or payload.get("fraction")
    if fraction is None:
        return None
    observed = float(fraction) > 0.01
    if not observed:
        return None
    return {
        "water_fraction": float(fraction),
        "status": "observed",
        "detail": payload.get("product_id") or "GFM Sentinel-1",
    }
