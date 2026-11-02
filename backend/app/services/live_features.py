import contextvars
import csv
import json
import math
import time
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx

from app.services import clients
from app.services.hydro_history import APP_HISTORY_START, GLOFAS_DISCHARGE_START
from app.services.hydro_local_store import attach_local_meteorology, local_observations_for_range

DailyObservation = tuple[date, float, float]
PROJECT_ROOT = Path(__file__).resolve().parents[3]
RIVER_POINTS_CSV = PROJECT_ROOT / "data" / "external" / "bago_river_points.csv"
MODEL_METADATA_PATH = PROJECT_ROOT / "ml" / "models" / "bago_flood_model_metadata.json"
CONTEXT_DAYS = 62
FORECAST_DAYS = 7
EXTERNAL_CALL_TIMEOUT_SECONDS = 3.5
_OBSERVATIONS_CACHE_TTL_SECONDS = 900
_observations_cache: dict[tuple[str, str, str], tuple[float, list[dict[str, Any]]]] = {}
_external_deadline: contextvars.ContextVar[float | None] = contextvars.ContextVar(
    "hydro_external_deadline",
    default=None,
)

NEW_MODEL_FEATURES = (
    "rainfall_1d_mm",
    "rainfall_3d_mm",
    "rainfall_7d_mm",
    "rainfall_14d_mm",
    "rainfall_30d_mm",
    "temperature_c",
    "relative_humidity_pct",
    "wind_speed_m_s",
    "latitude",
    "longitude",
    "day_of_year_sin",
    "day_of_year_cos",
    "discharge_lag_1d_m3s",
    "discharge_lag_3d_mean_m3s",
)
LAND_FEATURES = (
    "soil_moisture_0_to_7cm",
    "soil_moisture_7_to_28cm",
    "et0_fao_evapotranspiration",
)
LAND_CACHE_DIR = PROJECT_ROOT / "data" / "external" / "open_meteo_land"


@lru_cache(maxsize=1)
def river_points() -> tuple[dict[str, Any], ...]:
    if not RIVER_POINTS_CSV.is_file():
        return ()
    with RIVER_POINTS_CSV.open(encoding="utf-8", newline="") as handle:
        return tuple(dict(row) for row in csv.DictReader(handle))


@lru_cache(maxsize=1)
def trained_river_townships() -> frozenset[str]:
    if not MODEL_METADATA_PATH.is_file():
        return frozenset()
    payload = json.loads(MODEL_METADATA_PATH.read_text(encoding="utf-8"))
    return frozenset(str(name) for name in payload.get("townships", []))


def nearest_river_cell(latitude: float, longitude: float) -> dict[str, Any] | None:
    rows = river_points()
    if not rows:
        return None
    best = min(
        rows,
        key=lambda row: (float(row["weather_latitude"]) - latitude) ** 2
        + (float(row["weather_longitude"]) - longitude) ** 2,
    )
    return {
        "township": best["township"],
        "district": best["district"],
        "code": best["code"],
        "weather_latitude": float(best["weather_latitude"]),
        "weather_longitude": float(best["weather_longitude"]),
        "river_latitude": float(best["river_latitude"]),
        "river_longitude": float(best["river_longitude"]),
        "in_training_set": best["township"] in trained_river_townships(),
    }


def _first_number(*values: float | None) -> float | None:
    for value in values:
        if value is not None:
            return float(value)
    return None


def _normalize_observation(item: DailyObservation | dict[str, Any]) -> dict[str, Any]:
    if isinstance(item, dict):
        row = dict(item)
        row["date"] = item["date"]
        return row
    day, rain, discharge = item
    return {"date": day, "rainfall_mm": rain, "river_discharge_m3s": discharge}


def _window_sum(values: list[float | None], dates: list[date], index: int, size: int) -> float | None:
    start = index - size + 1
    if start < 0:
        return None
    if (dates[index] - dates[start]).days != size - 1:
        return None
    selected = values[start : index + 1]
    if any(value is None for value in selected):
        return None
    return float(sum(selected))


def _lagged_discharge(values: list[float | None], dates: list[date], index: int, offset: int) -> float | None:
    source = index - offset
    if source < 0 or (dates[index] - dates[source]).days != offset:
        return None
    value = values[source]
    return None if value is None else float(value)


async def load_observations(latitude: float, longitude: float) -> list[DailyObservation] | list[dict[str, Any]]:
    """Join Open-Meteo weather, NASA POWER meteorology, and GloFAS discharge."""
    river = nearest_river_cell(latitude, longitude)
    river_latitude = float(river["river_latitude"]) if river else latitude
    river_longitude = float(river["river_longitude"]) if river else longitude
    today = datetime.now(timezone.utc).date()
    history_start = today - timedelta(days=CONTEXT_DAYS)
    weather, discharge, nasa = await _fetch_live(
        latitude,
        longitude,
        river_latitude,
        river_longitude,
        history_start,
        today,
    )
    nasa_by_day = {point.date: point for point in nasa}
    weather_by_day = {item["date"]: item for item in weather}
    discharge_by_day = {day: value for day, value in discharge if value is not None}
    days = sorted(set(weather_by_day) | set(discharge_by_day) | set(nasa_by_day))
    observations: list[dict[str, Any]] = []
    for day in days:
        weather_row = weather_by_day.get(day, {})
        nasa_row = nasa_by_day.get(day)
        rain = _first_number(
            weather_row.get("rainfall_mm"),
            None if nasa_row is None else nasa_row.precipitation_mm,
        )
        discharge_value = discharge_by_day.get(day)
        if rain is None or discharge_value is None:
            continue
        observations.append(
            {
                "date": day,
                "rainfall_mm": rain,
                "river_discharge_m3s": discharge_value,
                "temperature_c": _first_number(
                    None if nasa_row is None else nasa_row.temperature_c,
                    weather_row.get("temperature_c"),
                ),
                "relative_humidity_pct": _first_number(
                    None if nasa_row is None else nasa_row.relative_humidity_pct,
                    weather_row.get("relative_humidity_pct"),
                ),
                "wind_speed_m_s": _first_number(
                    None if nasa_row is None else nasa_row.wind_speed_m_s,
                    weather_row.get("wind_speed_m_s"),
                ),
                "soil_moisture_0_to_7cm": weather_row.get("soil_moisture_0_to_7cm"),
                "soil_moisture_7_to_28cm": weather_row.get("soil_moisture_7_to_28cm"),
                "et0_fao_evapotranspiration": weather_row.get("et0_fao_evapotranspiration"),
                "rainfall_source": "Open-Meteo forecast/reanalysis"
                if weather_row.get("rainfall_mm") is not None
                else "NASA POWER PRECTOTCORR",
                "meteorology_source": "NASA POWER"
                if nasa_row is not None
                and nasa_row.temperature_c is not None
                else "Open-Meteo forecast/reanalysis",
                "discharge_source": "Open-Meteo Flood API modeled GloFAS-derived discharge",
                "river_township": None if river is None else river["township"],
                "in_training_set": False if river is None else river["in_training_set"],
            }
        )
    if not observations:
        raise ValueError("Weather APIs returned no complete rainfall and discharge days")
    return observations


async def _fetch_live(
    latitude: float,
    longitude: float,
    river_latitude: float,
    river_longitude: float,
    history_start: date,
    history_end: date,
):
    import asyncio

    weather_task = clients.open_meteo_daily_weather(
        latitude, longitude, CONTEXT_DAYS, FORECAST_DAYS
    )
    discharge_task = clients.glofas_daily_discharge(
        river_latitude, river_longitude, CONTEXT_DAYS, FORECAST_DAYS
    )
    nasa_task = clients.nasa_power_history_range(latitude, longitude, history_start, history_end)
    weather, discharge, nasa = await asyncio.gather(
        weather_task, discharge_task, nasa_task, return_exceptions=True
    )
    if isinstance(weather, Exception):
        raise weather
    if isinstance(discharge, Exception):
        raise discharge
    if isinstance(nasa, Exception):
        nasa = []
    return weather, discharge, nasa


async def _fetch_pair(latitude: float, longitude: float):
    import asyncio

    return await asyncio.gather(
        clients.open_meteo_daily_precipitation(latitude, longitude),
        clients.glofas_daily_discharge(latitude, longitude),
    )


def features_on_or_after(
    observations: list[DailyObservation] | list[dict[str, Any]],
    start: date,
    township_id: str,
    latitude: float,
    longitude: float,
) -> list[dict[str, float | str | date | None | bool]]:
    """Build model rows for the start date and every later API day. Earlier days are context only."""
    ordered = sorted((_normalize_observation(item) for item in observations), key=lambda row: row["date"])
    dates = [row["date"] for row in ordered]
    rains = [None if row.get("rainfall_mm") is None else float(row["rainfall_mm"]) for row in ordered]
    discharges = [
        None if row.get("river_discharge_m3s") is None else float(row["river_discharge_m3s"])
        for row in ordered
    ]
    rows: list[dict[str, float | str | date | None | bool]] = []
    for index, item in enumerate(ordered):
        day = item["date"]
        if day < start:
            continue
        rain = rains[index]
        discharge = discharges[index]
        if rain is None or discharge is None:
            continue
        rain_window = [value for value in rains[max(0, index - 6) : index + 1] if value is not None]
        discharge_window = [
            value for value in discharges[max(0, index - 2) : index + 1] if value is not None
        ]
        previous_rain = rains[index - 1] if index else 0.0
        previous_discharge = discharges[index - 1] if index else 0.0
        if previous_rain is None:
            previous_rain = 0.0
        if previous_discharge is None:
            previous_discharge = 0.0
        day_number = day.timetuple().tm_yday
        lag1 = _lagged_discharge(discharges, dates, index, 1)
        lag2 = _lagged_discharge(discharges, dates, index, 2)
        lag3 = _lagged_discharge(discharges, dates, index, 3)
        lag_mean = None if None in (lag1, lag2, lag3) else (lag1 + lag2 + lag3) / 3
        rows.append(
            {
                "date": day,
                "rainfall_mm": rain,
                "river_discharge_m3s": discharge,
                "rainfall_1d_mm": rain,
                "rainfall_3d_mm": _window_sum(rains, dates, index, 3) or sum(rain_window[-3:]),
                "rainfall_7d_mm": _window_sum(rains, dates, index, 7) or sum(rain_window),
                "rainfall_14d_mm": _window_sum(rains, dates, index, 14),
                "rainfall_30d_mm": _window_sum(rains, dates, index, 30),
                "rainfall_lag_1d_mm": previous_rain,
                "discharge_lag_1d_m3s": lag1 if lag1 is not None else previous_discharge,
                "discharge_delta_1d_m3s": discharge - previous_discharge,
                "discharge_3d_mean_m3s": sum(discharge_window) / len(discharge_window),
                "discharge_lag_3d_mean_m3s": lag_mean,
                "day_of_year_sin": math.sin(2 * math.pi * day_number / 365.25),
                "day_of_year_cos": math.cos(2 * math.pi * day_number / 365.25),
                "lat": latitude,
                "lng": longitude,
                "latitude": latitude,
                "longitude": longitude,
                "township_id": township_id,
                "temperature_c": item.get("temperature_c"),
                "relative_humidity_pct": item.get("relative_humidity_pct"),
                "wind_speed_m_s": item.get("wind_speed_m_s"),
                "soil_moisture_0_to_7cm": item.get("soil_moisture_0_to_7cm"),
                "soil_moisture_7_to_28cm": item.get("soil_moisture_7_to_28cm"),
                "et0_fao_evapotranspiration": item.get("et0_fao_evapotranspiration"),
                "rainfall_source": item.get("rainfall_source"),
                "meteorology_source": item.get("meteorology_source"),
                "discharge_source": item.get("discharge_source"),
                "river_township": item.get("river_township"),
                "in_training_set": bool(item.get("in_training_set")),
                "chirps_rainfall_mm": item.get("chirps_rainfall_mm"),
                "soil_moisture": item.get("soil_moisture"),
                "runoff": item.get("runoff"),
            }
        )
        # Centroid rainfall fills the upstream column until a northern river
        # proxy is available. Townships without that coordinate keep this
        # centroid-only fallback; the mode is stored on the feature payload.
        row = rows[-1]
        row["rainfall_upstream_1d_mm"] = rain
        row["rainfall_upstream_mode"] = "centroid_only_fallback"
        row.update(_location_prior_features(latitude, longitude, str(row.get("township_id") or township_id)))
    if not rows:
        from app.services.hydro_offline_db import hydrology_error_message

        end_hint = dates[-1] if dates else start
        raise ValueError(
            hydrology_error_message(
                window_start=start,
                window_end=end_hint,
                operational_start=APP_HISTORY_START,
            )
        )
    return rows


def row_has_model_features(row: dict[str, Any], feature_names: list[str] | tuple[str, ...] | None) -> bool:
    names = feature_names or NEW_MODEL_FEATURES
    return all(row.get(name) is not None for name in names)


@lru_cache(maxsize=1)
def _static_prior():
    import importlib.util

    path = PROJECT_ROOT / "ml" / "flood" / "static_prior.py"
    spec = importlib.util.spec_from_file_location("hydroflow_flood_static_prior", path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@lru_cache(maxsize=64)
def _cached_location_prior(latitude: float, longitude: float) -> tuple[tuple[str, float], ...]:
    module = _static_prior()
    rivers = module.load_river_points(RIVER_POINTS_CSV)
    features = module.point_features(float(latitude), float(longitude), rivers)
    return tuple((str(key), float(value)) for key, value in features.items())


def _location_prior_features(
    latitude: float, longitude: float, township_id: str | None = None
) -> dict[str, float]:
    """Centroid-to-river distance plus offline JRC/HAND/WorldCover when present."""
    merged: dict[str, float] = {}
    try:
        merged.update(dict(_cached_location_prior(round(float(latitude), 4), round(float(longitude), 4))))
    except Exception:
        pass
    if township_id:
        try:
            from app.services.hydro_offline_db import static_features

            for key, value in static_features(township_id).items():
                if key == "hazard_preview_path" or value is None:
                    continue
                merged[str(key)] = float(value)
        except Exception:
            pass
    return merged


def upstream_spec_for(
    latitude: float, longitude: float, township_id: str | None = None
) -> dict[str, Any]:
    """Upstream sample points, HydroBASINS id when ingested, or centroid fallback."""
    if township_id:
        try:
            from app.services.hydro_offline_db import static_features

            basin = static_features(township_id).get("hydrobasin_id")
            if basin:
                return {
                    "mode": "hydrobasins_offline",
                    "latitude": latitude,
                    "longitude": longitude,
                    "hydrobasin_id": basin,
                    "points": [],
                    "note": (
                        "Catchment-mean rainfall uses HydroBASINS basin id from "
                        "offline static ingest (CHIRPS/GloFAS aggregates when present)."
                    ),
                }
        except Exception:
            pass
    module = _static_prior()
    rivers = module.load_river_points(RIVER_POINTS_CSV)
    return module.upstream_spec(float(latitude), float(longitude), rivers)


async def fetch_upstream_mean(points: list[dict[str, Any]]) -> dict[date, float]:
    """Cache Open-Meteo rain at upstream river proxies and return the daily mean.

    Each proxy is stored in the hydro feature cache under source
    ``open-meteo-upstream``. Callers that have no points use centroid rainfall
    and record ``centroid_only_fallback`` on the feature payload.
    """
    from app.cache.hydro_features import upsert_daily_observation

    if not points:
        return {}
    series: list[dict[date, float]] = []
    for point in points:
        rows = await clients.open_meteo_daily_precipitation(
            float(point["latitude"]),
            float(point["longitude"]),
            past_days=CONTEXT_DAYS,
            forecast_days=FORECAST_DAYS,
        )
        daily: dict[date, float] = {}
        for day, value in rows:
            if value is None:
                continue
            daily[day] = float(value)
            try:
                upsert_daily_observation(
                    township_id=f"upstream:{point.get('township') or point['latitude']}",
                    observed_on=day,
                    source="open-meteo-upstream",
                    payload={
                        "rainfall_mm": float(value),
                        "latitude": float(point["latitude"]),
                        "longitude": float(point["longitude"]),
                        "code": point.get("code"),
                    },
                )
            except Exception:
                continue
        series.append(daily)
    dates: set[date] = set()
    for item in series:
        dates.update(item)
    averaged: dict[date, float] = {}
    for day in dates:
        values = [item[day] for item in series if day in item]
        if values:
            averaged[day] = sum(values) / len(values)
    return averaged


def cache_scored_features(
    township_id: str,
    observed_on: date,
    row: dict[str, Any],
    feature_version: str,
) -> None:
    """Write one Open-Meteo day, one GloFAS day, and the engineered row."""
    from app.cache.hydro_features import upsert_daily_observation, upsert_engineered_feature

    def _plain(value: Any) -> Any:
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        if isinstance(value, dict):
            return {str(key): _plain(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [_plain(item) for item in value]
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return None
        return value

    upsert_daily_observation(
        township_id=township_id,
        observed_on=observed_on,
        source="open-meteo",
        payload={
            "rainfall_mm": _plain(row.get("rainfall_mm")),
            "temperature_c": _plain(row.get("temperature_c")),
            "relative_humidity_pct": _plain(row.get("relative_humidity_pct")),
            "wind_speed_m_s": _plain(row.get("wind_speed_m_s")),
            "rainfall_upstream_1d_mm": _plain(row.get("rainfall_upstream_1d_mm")),
            "rainfall_upstream_mode": row.get("rainfall_upstream_mode"),
        },
    )
    upsert_daily_observation(
        township_id=township_id,
        observed_on=observed_on,
        source="glofas",
        payload={
            "river_discharge_m3s": _plain(row.get("river_discharge_m3s")),
            "discharge_lag_1d_m3s": _plain(row.get("discharge_lag_1d_m3s")),
            "discharge_lag_3d_mean_m3s": _plain(row.get("discharge_lag_3d_mean_m3s")),
        },
    )
    upsert_engineered_feature(
        township_id=township_id,
        observed_on=observed_on,
        feature_version=feature_version,
        payload=_plain({key: value for key, value in row.items() if key != "date"}),
    )


def _apply_weather_row(by_day: dict[date, dict[str, Any]], row: dict[str, date | float | None], *, source: str) -> None:
    day = row["date"]
    assert isinstance(day, date)
    existing = by_day.setdefault(day, {"date": day})
    if row.get("rainfall_mm") is not None:
        existing["rainfall_mm"] = float(row["rainfall_mm"])
        existing["rainfall_source"] = source
    for key in ("temperature_c", "relative_humidity_pct", "wind_speed_m_s"):
        if row.get(key) is not None:
            existing[key] = float(row[key])
    for key in LAND_FEATURES:
        if existing.get(key) is None and row.get(key) is not None:
            existing[key] = float(row[key])
    existing.setdefault("meteorology_source", source)


async def _fetch_reanalysis_window(
    latitude: float,
    longitude: float,
    river_latitude: float,
    river_longitude: float,
    start: date,
    end: date,
) -> tuple[list[dict[str, date | float | None]], list[tuple[date, float | None]]]:
    import asyncio

    weather_task = clients.open_meteo_archive_daily_weather(latitude, longitude, start, end)
    discharge_task = clients.resolve_glofas_discharge_daily(river_latitude, river_longitude, start, end)
    weather, discharge = await asyncio.gather(weather_task, discharge_task, return_exceptions=True)
    if isinstance(weather, Exception):
        weather = []
    if isinstance(discharge, Exception):
        discharge = []
    return weather, discharge


def _has_complete_hydro(by_day: dict[date, dict[str, Any]], start: date, end: date) -> bool:
    cursor = start
    while cursor <= end:
        row = by_day.get(cursor)
        if row is None or row.get("rainfall_mm") is None or row.get("river_discharge_m3s") is None:
            return False
        cursor += timedelta(days=1)
    return True


def _has_complete_land(by_day: dict[date, dict[str, Any]], start: date, end: date) -> bool:
    cursor = start
    while cursor <= end:
        row = by_day.get(cursor)
        if row is None or any(row.get(name) is None for name in LAND_FEATURES):
            return False
        cursor += timedelta(days=1)
    return True


@lru_cache(maxsize=64)
def _cached_land(township_id: str) -> tuple[tuple[date, tuple[tuple[str, float], ...]], ...]:
    path = LAND_CACHE_DIR / f"{township_id}.json"
    if not path.is_file():
        return ()
    payload = json.loads(path.read_text(encoding="utf-8"))
    daily = payload.get("daily") or {}
    times = daily.get("time") or []
    columns = {name: daily.get(name) or [] for name in LAND_FEATURES}
    rows: list[tuple[date, tuple[tuple[str, float], ...]]] = []
    for index, timestamp in enumerate(times):
        values: list[tuple[str, float]] = []
        for name, series in columns.items():
            if index >= len(series) or series[index] is None:
                values = []
                break
            values.append((name, float(series[index])))
        if len(values) == len(LAND_FEATURES):
            rows.append((date.fromisoformat(str(timestamp)[:10]), tuple(values)))
    return tuple(rows)


def _attach_land_cache(by_day: dict[date, dict[str, Any]], storage_ids: list[str]) -> None:
    """Fill historical soil moisture and ET0 from the training cache. Live values win."""
    for storage_id in storage_ids:
        for day, values in _cached_land(storage_id):
            row = by_day.get(day)
            if row is None:
                continue
            for name, value in values:
                if row.get(name) is None:
                    row[name] = value


def _served_model_needs_land() -> bool:
    if not MODEL_METADATA_PATH.is_file():
        return False
    payload = json.loads(MODEL_METADATA_PATH.read_text(encoding="utf-8"))
    listed = payload.get("features") or payload.get("model_features") or ()
    return any(name in listed for name in LAND_FEATURES)


def _finalize_observations(by_day: dict[date, dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        by_day[day]
        for day in sorted(by_day)
        if by_day[day].get("rainfall_mm") is not None and by_day[day].get("river_discharge_m3s") is not None
    ]


def offline_observations(
    township_id: str,
    latitude: float,
    longitude: float,
    window_start: date,
    window_end: date,
    *,
    catalog_township_id: str | None = None,
) -> list[dict[str, Any]]:
    """Local hydrology only. No Open-Meteo, GloFAS, or NASA calls.

    A short gap after the last on-disk day is filled forward so every township
    can be scored even when the shared request budget has already been spent.
    """
    catalog_id = catalog_township_id or township_id
    context_start = window_start - timedelta(days=CONTEXT_DAYS)
    # Skip the feature-cache database here. A locked cache must not stall scoring
    # when the merged hydrology files already cover the township.
    by_day = _load_offline_by_day(
        township_id,
        catalog_id,
        context_start,
        window_end,
        use_catalog=False,
        use_feature_cache=False,
        attach_meteorology=False,
    )
    river = nearest_river_cell(latitude, longitude)
    if river is not None:
        for row in by_day.values():
            row.setdefault("river_township", river["township"])
            row.setdefault("in_training_set", river["in_training_set"])
    score_start = window_start - timedelta(days=30)
    _forward_fill_hydro(by_day, score_start, window_end)
    _forward_fill_meteo(by_day, score_start, window_end)
    return _finalize_observations(by_day)


@contextmanager
def external_budget(seconds: float):
    """Bound Open-Meteo, GloFAS, and NASA calls started on this task."""
    token = _external_deadline.set(time.monotonic() + max(0.0, float(seconds)))
    try:
        yield
    finally:
        _external_deadline.reset(token)


def external_call_allowed() -> bool:
    deadline = _external_deadline.get()
    if deadline is None:
        return True
    return time.monotonic() < deadline


def external_remaining() -> float:
    deadline = _external_deadline.get()
    if deadline is None:
        return EXTERNAL_CALL_TIMEOUT_SECONDS
    return max(0.0, deadline - time.monotonic())


def _compact_id(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


# Romanization differences between admin slugs and on-disk hydro file names.
_STORAGE_ALIASES = {
    "okpho": "okpo",
    "okpo": "okpho",
    "pantaung": "padaung",
    "padaung": "pantaung",
    "paukkhaung": "paukkaung",
    "paukkaung": "paukkhaung",
    "phyu": "pyu",
    "pyu": "phyu",
}


def _remember_storage_id(index: dict[str, list[str]], key: str, stem: str) -> None:
    """Record every file that can answer a township key.

    P-code series are kept after short slug extracts so a stub file such as
    ``bago.csv`` does not hide the full merged series for the same township.
    """
    compact = _compact_id(key)
    if not compact:
        return

    def _add(bucket_key: str) -> None:
        bucket = index.setdefault(bucket_key, [])
        if stem in bucket:
            return
        if stem.upper().startswith("MMR"):
            bucket.append(stem)
        else:
            bucket.insert(0, stem)

    _add(compact)
    alias = _STORAGE_ALIASES.get(compact)
    if alias:
        _add(alias)


def _index_hydro_names(index: dict[str, list[str]], folder: Path) -> None:
    """Point township names inside each merged file at that file, not only the stem."""
    if not folder.is_dir():
        return
    for path in sorted(folder.glob("*.csv")):
        _remember_storage_id(index, path.stem, path.stem)
        try:
            with path.open(encoding="utf-8", newline="") as handle:
                row = next(csv.DictReader(handle), None)
        except OSError:
            continue
        if not row:
            continue
        for key in (row.get("township"), row.get("township_id")):
            if key:
                _remember_storage_id(index, str(key), path.stem)


@lru_cache(maxsize=1)
def _storage_id_index() -> dict[str, list[str]]:
    """Map punctuation-free township keys onto validated_daily and local file ids."""
    index: dict[str, list[str]] = {}
    try:
        from app.services.daily_catalog import _frame

        for township_id in _frame()["township_id"].dropna().unique():
            _remember_storage_id(index, str(township_id), str(township_id))
    except Exception:
        pass
    from app.services.hydro_sources import GLOFAS_DISCHARGE_DIR, HYDRO_MERGED_DIR, OPEN_METEO_ARCHIVE_DIR

    _index_hydro_names(index, HYDRO_MERGED_DIR)
    for folder in (OPEN_METEO_ARCHIVE_DIR, GLOFAS_DISCHARGE_DIR):
        if not folder.is_dir():
            continue
        for path in folder.glob("*.csv"):
            _remember_storage_id(index, path.stem, path.stem)
    return index


def storage_ids_for(township_id: str, catalog_township_id: str | None = None) -> list[str]:
    index = _storage_id_index()
    found: list[str] = []
    for raw in (catalog_township_id, township_id):
        if not raw:
            continue
        text = str(raw).strip()
        for item in index.get(_compact_id(text), []):
            if item not in found:
                found.append(item)
        if text not in found:
            found.append(text)
    return found or [township_id]


def _clone_persisted(source: dict[str, Any], day: date) -> dict[str, Any]:
    cloned = dict(source)
    cloned["date"] = day
    cloned["rainfall_source"] = "persisted local hydrology"
    cloned["discharge_source"] = "persisted local hydrology"
    cloned["meteorology_source"] = source.get("meteorology_source") or "persisted local hydrology"
    return cloned


def _row_has_hydro(row: dict[str, Any] | None) -> bool:
    return row is not None and row.get("rainfall_mm") is not None and row.get("river_discharge_m3s") is not None


def _forward_fill_hydro(by_day: dict[date, dict[str, Any]], start: date, end: date) -> None:
    """Copy the last on-disk rain and discharge across a short or long gap. No HTTP."""
    previous: dict[str, Any] | None = None
    for day in sorted(by_day):
        if day >= start:
            break
        if _row_has_hydro(by_day[day]):
            previous = by_day[day]
    cursor = start
    while cursor <= end:
        current = by_day.get(cursor)
        if _row_has_hydro(current):
            previous = current
        elif previous is not None:
            filled = _clone_persisted(previous, cursor)
            if current is not None:
                for key, value in current.items():
                    if value is not None and key != "date":
                        filled[key] = value
                filled["date"] = cursor
            by_day[cursor] = filled
            previous = filled
        cursor += timedelta(days=1)


def _forward_fill_meteo(by_day: dict[date, dict[str, Any]], start: date, end: date) -> None:
    last: dict[str, float] = {}
    for day in sorted(by_day):
        if day < start:
            row = by_day[day]
            for key in ("temperature_c", "relative_humidity_pct", "wind_speed_m_s"):
                if row.get(key) is not None:
                    last[key] = float(row[key])
    cursor = start
    while cursor <= end:
        row = by_day.get(cursor)
        if row is not None:
            for key in ("temperature_c", "relative_humidity_pct", "wind_speed_m_s"):
                if row.get(key) is None and key in last:
                    row[key] = last[key]
                elif row.get(key) is not None:
                    last[key] = float(row[key])
        cursor += timedelta(days=1)


def _cached_daily_rows(township_id: str, start: date, end: date) -> list[dict[str, Any]]:
    """Engineered rows and raw provider days already stored in the hydro feature cache."""
    try:
        from app.cache.hydro_features import DailyObservation, EngineeredFeature, feature_engine
        from sqlalchemy import select
        from sqlalchemy.orm import Session
    except Exception:
        return []
    rows: list[dict[str, Any]] = []
    try:
        with Session(feature_engine()) as cache:
            engineered = cache.scalars(
                select(EngineeredFeature).where(
                    EngineeredFeature.township_id == township_id,
                    EngineeredFeature.observed_on >= start,
                    EngineeredFeature.observed_on <= end,
                )
            ).all()
            for item in engineered:
                if not isinstance(item.payload, dict):
                    continue
                payload = dict(item.payload)
                payload["date"] = item.observed_on
                rows.append(payload)
            observed = cache.scalars(
                select(DailyObservation).where(
                    DailyObservation.township_id == township_id,
                    DailyObservation.observed_on >= start,
                    DailyObservation.observed_on <= end,
                    DailyObservation.source.in_(("open-meteo", "glofas", "validated_daily")),
                )
            ).all()
            for item in observed:
                if not isinstance(item.payload, dict):
                    continue
                payload = dict(item.payload)
                payload["date"] = item.observed_on
                rows.append(payload)
    except Exception:
        return rows
    return rows


def _load_offline_by_day(
    township_id: str,
    catalog_township_id: str | None,
    start: date,
    end: date,
    *,
    use_catalog: bool = True,
    use_feature_cache: bool = True,
    attach_meteorology: bool = True,
) -> dict[date, dict[str, Any]]:
    from app.services.daily_catalog import catalog_observations_for_range
    from app.services.hydro_offline_db import forecast_for_range, observations_for_range as offline_range

    by_day: dict[date, dict[str, Any]] = {}
    for row in offline_range(township_id, start, end):
        day = row["date"]
        by_day[day] = {**by_day.get(day, {"date": day}), **dict(row)}
    storage_ids = storage_ids_for(township_id, catalog_township_id)
    for storage_id in storage_ids:
        if use_catalog:
            try:
                for row in catalog_observations_for_range(storage_id, start, end):
                    day = row["date"]
                    by_day[day] = {**by_day.get(day, {"date": day}), **dict(row)}
            except FileNotFoundError:
                pass
        for row in local_observations_for_range(storage_id, start, end):
            day = row["date"]
            by_day[day] = {**by_day.get(day, {"date": day}), **row}
        if use_feature_cache:
            for row in _cached_daily_rows(storage_id, start, end):
                day = row["date"]
                by_day[day] = {**by_day.get(day, {"date": day}), **row}
        if attach_meteorology:
            attach_local_meteorology(by_day, storage_id, start, end)
    _attach_land_cache(by_day, storage_ids)
    today = datetime.now(timezone.utc).date()
    if end >= today:
        for row in forecast_for_range(township_id, max(start, today), end, as_of=today):
            day = row["date"]
            by_day[day] = {**by_day.get(day, {"date": day}), **row}
    return by_day


async def _supplement_from_providers(
    by_day: dict[date, dict[str, Any]],
    *,
    latitude: float,
    longitude: float,
    river_latitude: float,
    river_longitude: float,
    river: dict[str, Any] | None,
    start: date,
    end: date,
    historical_only: bool,
) -> None:
    """One short provider attempt. Callers cancel this with asyncio.wait_for."""
    reanalysis_end = min(end, datetime.now(timezone.utc).date())
    if start <= reanalysis_end:
        try:
            weather, discharge = await _fetch_reanalysis_window(
                latitude,
                longitude,
                river_latitude,
                river_longitude,
                max(start, GLOFAS_DISCHARGE_START),
                reanalysis_end,
            )
        except (httpx.HTTPError, ValueError):
            weather, discharge = [], []
        for row in weather:
            _apply_weather_row(by_day, row, source="Open-Meteo ERA5 archive")
        for day, value in discharge:
            if value is None:
                continue
            existing = by_day.setdefault(day, {"date": day})
            existing["river_discharge_m3s"] = float(value)
            existing["discharge_source"] = "Open-Meteo Flood API GloFAS (default reanalysis + fallbacks)"
            if river is not None:
                existing.setdefault("river_township", river["township"])
                existing.setdefault("in_training_set", river["in_training_set"])
    if historical_only:
        return
    try:
        live = await load_observations(latitude, longitude)
    except (httpx.HTTPError, ValueError):
        live = []
    for row in live:
        if not isinstance(row, dict):
            continue
        day = row.get("date")
        if isinstance(day, date) and start <= day <= end:
            by_day[day] = {**by_day.get(day, {"date": day}), **row}


async def observations_for_timeline(
    township_id: str,
    latitude: float,
    longitude: float,
    window_start: date,
    window_end: date,
    *,
    catalog_township_id: str | None = None,
) -> list[dict[str, Any]]:
    """Merge local hydrology first. External calls are skipped when that series can be scored.

    validated_daily.csv, the hydro feature cache, and on-disk Open-Meteo / GloFAS extracts
    supply the window. A gap after the last local day is filled by persisting that day.
    Open-Meteo, GloFAS, and NASA are attempted only when the local series still cannot
    cover the requested dates, and only inside the active external budget.
    """
    import asyncio

    catalog_id = catalog_township_id or township_id
    today = datetime.now(timezone.utc).date()
    context_start = window_start - timedelta(days=CONTEXT_DAYS)
    historical_only = window_end < today
    fetch_end = window_end if historical_only else max(window_end, today + timedelta(days=FORECAST_DAYS))
    cache_key = (catalog_id, context_start.isoformat(), fetch_end.isoformat())
    now = time.monotonic()
    cached = _observations_cache.get(cache_key)
    if cached is not None and now - cached[0] < _OBSERVATIONS_CACHE_TTL_SECONDS:
        return cached[1]

    river = nearest_river_cell(latitude, longitude)
    river_latitude = float(river["river_latitude"]) if river else latitude
    river_longitude = float(river["river_longitude"]) if river else longitude
    by_day = _load_offline_by_day(township_id, catalog_id, context_start, fetch_end)
    if river is not None:
        for row in by_day.values():
            row.setdefault("river_township", river["township"])
            row.setdefault("in_training_set", river["in_training_set"])

    score_start = window_start - timedelta(days=30)

    def _cover_from_disk() -> None:
        _forward_fill_hydro(by_day, score_start, window_end)
        _forward_fill_meteo(by_day, score_start, window_end)

    _cover_from_disk()
    hydro_ready = _has_complete_hydro(by_day, score_start, window_end)
    land_ready = not _served_model_needs_land() or _has_complete_land(by_day, score_start, window_end)
    if hydro_ready and land_ready:
        result = _finalize_observations(by_day)
        _observations_cache[cache_key] = (now, result)
        return result

    if external_call_allowed():
        if historical_only:
            remaining = external_remaining()
            timeout = min(90.0, remaining) if remaining > 0 else 90.0
        else:
            timeout = min(EXTERNAL_CALL_TIMEOUT_SECONDS, external_remaining())
        if timeout >= 0.2:
            try:
                await asyncio.wait_for(
                    _supplement_from_providers(
                        by_day,
                        latitude=latitude,
                        longitude=longitude,
                        river_latitude=river_latitude,
                        river_longitude=river_longitude,
                        river=river,
                        start=score_start,
                        end=window_end,
                        historical_only=historical_only,
                    ),
                    timeout=timeout,
                )
            except (TimeoutError, asyncio.TimeoutError, httpx.HTTPError, ValueError):
                pass
            _cover_from_disk()

    result = _finalize_observations(by_day)
    _observations_cache[cache_key] = (now, result)
    return result
