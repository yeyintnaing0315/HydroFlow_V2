import asyncio
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

import httpx

from app.schemas.api import ForecastPoint, HistoricalPoint

TIMEOUT_SECONDS = 10.0
NASA_POWER_TIMEOUT_SECONDS = 45.0
ARCHIVE_TIMEOUT_SECONDS = 120.0
FLOOD_ARCHIVE_TIMEOUT_SECONDS = 120.0
NASA_POWER_PARAMETERS = "PRECTOTCORR,T2M,RH2M,WS2M"
REANALYSIS_CHUNK_DAYS = 730
NASA_CHUNK_DAYS = 1095
GLOFAS_PAST_DAYS_MAX = 365
FLOOD_API_URL = "https://flood-api.open-meteo.com/v1/flood"
# Daily means of the ERA5-Land layers. The same names exist on the forecast API.
LAND_API_FIELDS = {
    "soil_moisture_0_to_7cm": "soil_moisture_0_to_7cm_mean",
    "soil_moisture_7_to_28cm": "soil_moisture_7_to_28cm_mean",
    "et0_fao_evapotranspiration": "et0_fao_evapotranspiration",
}
DAILY_WEATHER_VARIABLES = ",".join(
    (
        "precipitation_sum",
        "temperature_2m_mean",
        "relative_humidity_2m_mean",
        "wind_speed_10m_mean",
        *LAND_API_FIELDS.values(),
    )
)
POINT_ELEVATION_URL = "https://portal.opentopography.org/API/v1/elevation"
ELEVATION_DATASET = "COP30"
_elevation_cache: dict[tuple[float, float, str], dict[str, float | str]] = {}


class OpenTopographyConfigError(RuntimeError):
    """Raised when the OpenTopography key is missing."""


def _load_project_env() -> None:
    """Fill unset variables from the project .env. Existing variables win."""
    path = Path(__file__).resolve().parents[3] / ".env"
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


def redact_secret(message: str) -> str:
    _load_project_env()
    redacted = message
    for name in ("OPENTOPOGRAPHY_API_KEY", "KARDINAL_API_KEY"):
        key = os.getenv(name, "").strip()
        if key:
            redacted = redacted.replace(key, "[redacted]")
    return redacted


def _opentopography_key() -> str:
    _load_project_env()
    key = os.getenv("OPENTOPOGRAPHY_API_KEY", "").strip()
    if not key:
        raise OpenTopographyConfigError("OPENTOPOGRAPHY_API_KEY is not set")
    return key


def _number(value: Any) -> float | None:
    if value is None:
        return None
    number = float(value)
    return None if number == -999 else number


def _aligned_series(daily: dict[str, Any], key: str, count: int) -> list[Any]:
    """Return one daily array, or blanks when an optional land field is absent."""
    series = daily.get(key)
    if not isinstance(series, list) or len(series) != count:
        return [None] * count
    return series


async def nasa_power_history(
    latitude: float, longitude: float, start: date, end: date
) -> list[HistoricalPoint]:
    params = {
        "parameters": NASA_POWER_PARAMETERS,
        "community": "AG",
        "longitude": longitude,
        "latitude": latitude,
        "start": start.strftime("%Y%m%d"),
        "end": end.strftime("%Y%m%d"),
        "format": "JSON",
        "time-standard": "UTC",
    }
    async with httpx.AsyncClient(timeout=NASA_POWER_TIMEOUT_SECONDS) as client:
        response = await client.get("https://power.larc.nasa.gov/api/temporal/daily/point", params=params)
        response.raise_for_status()
    try:
        values = response.json()["properties"]["parameter"]
        precipitation = values["PRECTOTCORR"]
        temperature = values["T2M"]
        humidity = values["RH2M"]
        wind = values.get("WS2M") or {}
        keys = sorted(set(precipitation) | set(temperature) | set(humidity) | set(wind))
        return [
            HistoricalPoint(
                date=datetime.strptime(key, "%Y%m%d").date(),
                precipitation_mm=_number(precipitation.get(key)),
                temperature_c=_number(temperature.get(key)),
                relative_humidity_pct=_number(humidity.get(key)),
                wind_speed_m_s=_number(wind.get(key)) if wind else None,
            )
            for key in keys
        ]
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Invalid NASA POWER response") from exc


def _date_chunks(start: date, end: date, chunk_days: int) -> Iterator[tuple[date, date]]:
    if start > end:
        return
    cursor = start
    while cursor <= end:
        chunk_end = min(end, cursor + timedelta(days=chunk_days - 1))
        yield cursor, chunk_end
        cursor = chunk_end + timedelta(days=1)


async def nasa_power_history_range(
    latitude: float, longitude: float, start: date, end: date
) -> list[HistoricalPoint]:
    """NASA POWER daily point API with multi-year chunking."""
    if start > end:
        return []
    by_day: dict[date, HistoricalPoint] = {}
    for chunk_start, chunk_end in _date_chunks(start, end, NASA_CHUNK_DAYS):
        try:
            for point in await nasa_power_history(latitude, longitude, chunk_start, chunk_end):
                by_day[point.date] = point
        except (httpx.HTTPError, ValueError):
            continue
    return [by_day[day] for day in sorted(by_day)]


async def open_meteo_forecast(latitude: float, longitude: float) -> list[ForecastPoint]:
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": "temperature_2m,precipitation,relative_humidity_2m,wind_speed_10m",
        "forecast_days": 7,
        "timezone": "UTC",
        "wind_speed_unit": "ms",
    }
    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
        response = await client.get("https://api.open-meteo.com/v1/forecast", params=params)
        response.raise_for_status()
    try:
        hourly = response.json()["hourly"]
        times = hourly["time"]
        precipitation = hourly["precipitation"]
        temperature = hourly["temperature_2m"]
        humidity = hourly.get("relative_humidity_2m") or [None] * len(times)
        wind = hourly.get("wind_speed_10m") or [None] * len(times)
        if not (len(times) == len(precipitation) == len(temperature) == len(humidity) == len(wind)):
            raise ValueError
        return [
            ForecastPoint(
                timestamp=datetime.fromisoformat(timestamp).replace(tzinfo=timezone.utc),
                precipitation_mm=_number(precipitation[index]),
                temperature_c=_number(temperature[index]),
                relative_humidity_pct=_number(humidity[index]),
                wind_speed_m_s=_number(wind[index]),
            )
            for index, timestamp in enumerate(times)
        ]
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Invalid Open-Meteo forecast response") from exc


async def _request_json(url: str, params: dict[str, object], timeout: float = 20.0) -> dict[str, Any]:
    last_error: Exception | None = None
    for delay in (0, 8, 20):
        if delay:
            await asyncio.sleep(delay)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(url, params=params)
                if response.status_code in {429, 503}:
                    last_error = httpx.HTTPStatusError(
                        f"{response.status_code} {response.reason_phrase}",
                        request=response.request,
                        response=response,
                    )
                    continue
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ValueError(f"Invalid JSON object from {url}")
                return payload
        except (httpx.HTTPError, ValueError) as exc:
            last_error = exc
    assert last_error is not None
    raise last_error


async def _daily_values(
    url: str, params: dict[str, object], value_key: str
) -> list[tuple[date, float | None]]:
    payload = await _request_json(url, params)
    try:
        daily = payload["daily"]
        times = daily["time"]
        values = daily[value_key]
        if len(times) != len(values):
            raise ValueError
        return [
            (datetime.fromisoformat(timestamp).date(), _number(values[index]))
            for index, timestamp in enumerate(times)
        ]
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid daily response from {url}") from exc


async def open_meteo_daily_precipitation(
    latitude: float, longitude: float, past_days: int = 7, forecast_days: int = 7
) -> list[tuple[date, float | None]]:
    return await _daily_values(
        "https://api.open-meteo.com/v1/forecast",
        {
            "latitude": latitude,
            "longitude": longitude,
            "daily": "precipitation_sum",
            "past_days": past_days,
            "forecast_days": forecast_days,
            "timezone": "UTC",
        },
        "precipitation_sum",
    )


async def open_meteo_daily_weather(
    latitude: float, longitude: float, past_days: int = 62, forecast_days: int = 7
) -> list[dict[str, date | float | None]]:
    """Daily rainfall plus meteorology from the Open-Meteo forecast/reanalysis API."""
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "daily": DAILY_WEATHER_VARIABLES,
        "past_days": past_days,
        "forecast_days": forecast_days,
        "timezone": "UTC",
        "wind_speed_unit": "ms",
    }
    payload = await _request_json("https://api.open-meteo.com/v1/forecast", params)
    try:
        daily = payload["daily"]
        times = daily["time"]
        rainfall = daily["precipitation_sum"]
        temperature = daily["temperature_2m_mean"]
        humidity = daily["relative_humidity_2m_mean"]
        wind = daily["wind_speed_10m_mean"]
        count = len(times)
        if not (count == len(rainfall) == len(temperature) == len(humidity) == len(wind)):
            raise ValueError
        shallow = _aligned_series(daily, LAND_API_FIELDS["soil_moisture_0_to_7cm"], count)
        deeper = _aligned_series(daily, LAND_API_FIELDS["soil_moisture_7_to_28cm"], count)
        evapotranspiration = _aligned_series(daily, "et0_fao_evapotranspiration", count)
        return [
            {
                "date": datetime.fromisoformat(timestamp).date(),
                "rainfall_mm": _number(rainfall[index]),
                "temperature_c": _number(temperature[index]),
                "relative_humidity_pct": _number(humidity[index]),
                "wind_speed_m_s": _number(wind[index]),
                "soil_moisture_0_to_7cm": _number(shallow[index]),
                "soil_moisture_7_to_28cm": _number(deeper[index]),
                "et0_fao_evapotranspiration": _number(evapotranspiration[index]),
            }
            for index, timestamp in enumerate(times)
        ]
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Invalid Open-Meteo daily weather response") from exc


async def open_meteo_archive_daily_weather(
    latitude: float, longitude: float, start: date, end: date
) -> list[dict[str, date | float | None]]:
    """ERA5-based daily met from the Open-Meteo historical archive API."""
    if start > end:
        return []
    merged: dict[date, dict[str, date | float | None]] = {}
    params_base = {
        "latitude": latitude,
        "longitude": longitude,
        "daily": DAILY_WEATHER_VARIABLES,
        "timezone": "UTC",
        "wind_speed_unit": "ms",
    }
    for chunk_start, chunk_end in _date_chunks(start, end, REANALYSIS_CHUNK_DAYS):
        params = {
            **params_base,
            "start_date": chunk_start.isoformat(),
            "end_date": chunk_end.isoformat(),
        }
        payload = await _request_json(
            "https://archive-api.open-meteo.com/v1/archive",
            params,
            timeout=ARCHIVE_TIMEOUT_SECONDS,
        )
        try:
            daily = payload["daily"]
            times = daily["time"]
            rainfall = daily["precipitation_sum"]
            temperature = daily["temperature_2m_mean"]
            humidity = daily["relative_humidity_2m_mean"]
            wind = daily["wind_speed_10m_mean"]
            count = len(times)
            if not (count == len(rainfall) == len(temperature) == len(humidity) == len(wind)):
                raise ValueError
            shallow = _aligned_series(daily, LAND_API_FIELDS["soil_moisture_0_to_7cm"], count)
            deeper = _aligned_series(daily, LAND_API_FIELDS["soil_moisture_7_to_28cm"], count)
            evapotranspiration = _aligned_series(daily, "et0_fao_evapotranspiration", count)
            for index, timestamp in enumerate(times):
                day = datetime.fromisoformat(timestamp).date()
                merged[day] = {
                    "date": day,
                    "rainfall_mm": _number(rainfall[index]),
                    "temperature_c": _number(temperature[index]),
                    "relative_humidity_pct": _number(humidity[index]),
                    "wind_speed_m_s": _number(wind[index]),
                    "soil_moisture_0_to_7cm": _number(shallow[index]),
                    "soil_moisture_7_to_28cm": _number(deeper[index]),
                    "et0_fao_evapotranspiration": _number(evapotranspiration[index]),
                }
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Invalid Open-Meteo archive daily weather response") from exc
    return [merged[day] for day in sorted(merged)]


async def _glofas_discharge_date_range(
    latitude: float,
    longitude: float,
    start: date,
    end: date,
    *,
    models: str | None,
) -> dict[date, float | None]:
    today = datetime.now(timezone.utc).date()
    merged: dict[date, float | None] = {}
    for chunk_start, chunk_end in _date_chunks(start, end, REANALYSIS_CHUNK_DAYS):
        params: dict[str, object] = {
            "latitude": latitude,
            "longitude": longitude,
            "daily": "river_discharge",
            "start_date": chunk_start.isoformat(),
            "end_date": chunk_end.isoformat(),
        }
        if models:
            params["models"] = models
        if chunk_end >= today:
            params["forecast_days"] = max(0, (chunk_end - today).days)
        else:
            params["forecast_days"] = 0
        rows = await _daily_values(FLOOD_API_URL, params, "river_discharge")
        for day, value in rows:
            merged[day] = value
    return merged


async def resolve_glofas_discharge_daily(
    latitude: float, longitude: float, start: date, end: date
) -> list[tuple[date, float | None]]:
    """Best-effort GloFAS discharge for a calendar window.

    Open-Meteo's default flood model (no ``models`` param) covers recent years including
    2026. ``consolidated_v4`` alone often returns null for recent dates; it is used only
    to back-fill gaps. ``past_days`` covers any remaining holes near the present.
    """
    if start > end:
        return []
    merged = await _glofas_discharge_date_range(latitude, longitude, start, end, models=None)
    missing = [day for day, value in merged.items() if value is None]
    if missing:
        gap_start, gap_end = min(missing), max(missing)
        legacy = await _glofas_discharge_date_range(
            latitude, longitude, gap_start, gap_end, models="consolidated_v4"
        )
        for day, value in legacy.items():
            if merged.get(day) is None and value is not None:
                merged[day] = value

    today = datetime.now(timezone.utc).date()
    still_missing = [day for day in sorted(merged) if merged[day] is None and day <= today]
    if still_missing and start <= today:
        past_days = min(GLOFAS_PAST_DAYS_MAX, (today - min(start, still_missing[0])).days + 1)
        forecast_days = max(0, (end - today).days)
        try:
            for day, value in await glofas_daily_discharge(
                latitude, longitude, past_days=past_days, forecast_days=forecast_days
            ):
                if start <= day <= end and value is not None and merged.get(day) is None:
                    merged[day] = value
        except (httpx.HTTPError, ValueError):
            pass

    cursor = start
    output: list[tuple[date, float | None]] = []
    while cursor <= end:
        output.append((cursor, merged.get(cursor)))
        cursor += timedelta(days=1)
    return output


async def glofas_discharge_daily_range(
    latitude: float, longitude: float, start: date, end: date
) -> list[tuple[date, float | None]]:
    """GloFAS river discharge via Open-Meteo Flood API (multi-strategy resolver)."""
    return await resolve_glofas_discharge_daily(latitude, longitude, start, end)


async def glofas_daily_discharge(
    latitude: float, longitude: float, past_days: int = 7, forecast_days: int = 7
) -> list[tuple[date, float | None]]:
    return await _daily_values(
        FLOOD_API_URL,
        {
            "latitude": latitude,
            "longitude": longitude,
            "daily": "river_discharge",
            "past_days": past_days,
            "forecast_days": forecast_days,
        },
        "river_discharge",
    )


async def glofas_discharge_forecast(latitude: float, longitude: float) -> list[ForecastPoint]:
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "daily": "river_discharge",
        "forecast_days": 7,
    }
    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
        response = await client.get("https://flood-api.open-meteo.com/v1/flood", params=params)
        response.raise_for_status()
    try:
        daily = response.json()["daily"]
        times = daily["time"]
        discharge = daily["river_discharge"]
        if len(times) != len(discharge):
            raise ValueError
        return [
            ForecastPoint(
                timestamp=datetime.fromisoformat(timestamp).replace(tzinfo=timezone.utc),
                discharge_m3_s=_number(discharge[index]),
            )
            for index, timestamp in enumerate(times)
        ]
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Invalid GloFAS discharge response") from exc


async def opentopography_elevation(
    latitude: float, longitude: float, dataset: str = ELEVATION_DATASET
) -> dict[str, float | str]:
    """Return Copernicus surface elevation in meters for one WGS84 point.

    Results are cached so repeated township views stay inside the daily
    OpenTopography point-query limit. The value is terrain context, not a
    flood-model feature.
    """
    key = _opentopography_key()
    cache_key = (round(latitude, 5), round(longitude, 5), dataset)
    cached = _elevation_cache.get(cache_key)
    if cached is not None:
        return cached
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "dataset": dataset,
        "API_Key": key,
    }
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(POINT_ELEVATION_URL, params=params)
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPError as exc:
        raise ValueError(redact_secret("OpenTopography request failed")) from exc
    try:
        elevation = float(payload["Elevation"])
        shortname = str(payload.get("Shortname") or dataset)
        epsg = str(payload.get("VCRS_EPSG") or "")
        unit = str(payload.get("Unit") or "Meters")
        if not epsg or unit.lower() != "meters":
            raise ValueError
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Invalid OpenTopography elevation response") from exc
    point: dict[str, float | str] = {
        "elevation_m": elevation,
        "dataset": shortname,
        "vertical_datum_epsg": epsg,
        "unit": "Meters",
    }
    _elevation_cache[cache_key] = point
    return point
