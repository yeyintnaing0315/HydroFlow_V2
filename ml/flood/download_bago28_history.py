"""Download 2000-present Open-Meteo and GloFAS series for Bago's 28 townships.

Weather is the township centroid from the boundary file. Discharge uses the
river point in bago_river_points.csv when that township is listed, the
validated-daily coordinate when that township already had one, and otherwise
the nearest of those existing points. Madauk is downloaded only so the old
22-township test can still be scored. It is not one of the 28.

Each request is cached under data/external/bago28_chunks. A rerun skips chunks
that are already on disk. The merged daily file is rewritten only after every
chunk for that township has been stored.
"""

from __future__ import annotations

import json
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
BOUNDARY = ROOT / "data" / "external" / "geography" / "bago_township_boundaries.geojson"
RIVER_POINTS = ROOT / "data" / "external" / "bago_river_points.csv"
VALIDATED = ROOT / "data" / "processed" / "validated_daily.csv"
CHUNK_DIR = ROOT / "data" / "external" / "bago28_chunks"
MERGED_DIR = ROOT / "data" / "external" / "hydro_merged"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FLOOD_URL = "https://flood-api.open-meteo.com/v1/flood"
HISTORY_START = date(2000, 1, 1)
CHUNK_DAYS = 730
# Official 28. Madauk is outside this list.
OFFICIAL = (
    "Bago",
    "Kawa",
    "Thanatpin",
    "Waw",
    "Nyaunglebin",
    "Kyauktaga",
    "Daik-U",
    "Shwegyin",
    "Kyaukkyi",
    "Taungoo",
    "Oktwin",
    "Yedashe",
    "Pyu",
    "Htantabin",
    "Thayarwady",
    "Letpadan",
    "Minhla",
    "Monyo",
    "Okpo",
    "Gyobingauk",
    "Nattalin",
    "Zigon",
    "Thegon",
    "Paungde",
    "Pyay",
    "Paukkaung",
    "Padaung",
    "Shwedaung",
)
WEATHER_DAILY = ",".join(
    (
        "precipitation_sum",
        "temperature_2m_mean",
        "relative_humidity_2m_mean",
        "wind_speed_10m_mean",
        "soil_moisture_0_to_7cm_mean",
        "soil_moisture_7_to_28cm_mean",
        "et0_fao_evapotranspiration",
    )
)
MERGED_COLUMNS = (
    "date",
    "precipitation_mm",
    "temperature_c",
    "relative_humidity_pct",
    "wind_speed_m_s",
    "river_discharge_m3s",
    "rainfall_mm",
    "township_id",
    "township",
    "latitude",
    "longitude",
    "soil_moisture_0_to_7cm",
    "soil_moisture_7_to_28cm",
    "et0_fao_evapotranspiration",
    "discharge_latitude",
    "discharge_longitude",
    "weather_source",
    "et0_donor",
)


def _slug(name: str) -> str:
    cleaned = "".join(character.lower() if character.isalnum() else "_" for character in name.strip())
    return "_".join(part for part in cleaned.split("_") if part)


def _yesterday() -> date:
    return date.today() - timedelta(days=1)


def _chunks(start: date, end: date) -> list[tuple[date, date]]:
    rows: list[tuple[date, date]] = []
    cursor = start
    while cursor <= end:
        chunk_end = min(end, cursor + timedelta(days=CHUNK_DAYS - 1))
        rows.append((cursor, chunk_end))
        cursor = chunk_end + timedelta(days=1)
    return rows


def _ring_area(ring: list[list[float]]) -> float:
    area = 0.0
    for index in range(len(ring) - 1):
        x1, y1 = ring[index][0], ring[index][1]
        x2, y2 = ring[index + 1][0], ring[index + 1][1]
        area += x1 * y2 - x2 * y1
    return area / 2.0


def _ring_centroid(ring: list[list[float]]) -> tuple[float, float]:
    area = _ring_area(ring)
    if abs(area) < 1e-12:
        lon = sum(point[0] for point in ring) / len(ring)
        lat = sum(point[1] for point in ring) / len(ring)
        return lat, lon
    lon_sum = 0.0
    lat_sum = 0.0
    for index in range(len(ring) - 1):
        x1, y1 = ring[index][0], ring[index][1]
        x2, y2 = ring[index + 1][0], ring[index + 1][1]
        cross = x1 * y2 - x2 * y1
        lon_sum += (x1 + x2) * cross
        lat_sum += (y1 + y2) * cross
    return lat_sum / (6.0 * area), lon_sum / (6.0 * area)


def _largest_ring(geometry: dict) -> list[list[float]]:
    kind = geometry["type"]
    coordinates = geometry["coordinates"]
    if kind == "Polygon":
        return max(coordinates, key=lambda ring: abs(_ring_area(ring)))
    if kind == "MultiPolygon":
        rings = [ring for polygon in coordinates for ring in polygon]
        return max(rings, key=lambda ring: abs(_ring_area(ring)))
    raise ValueError(f"Unsupported geometry {kind}")


def _centroids() -> dict[str, tuple[float, float]]:
    payload = json.loads(BOUNDARY.read_text(encoding="utf-8"))
    found: dict[str, tuple[float, float]] = {}
    for feature in payload["features"]:
        name = str(feature["properties"]["name_en"])
        latitude, longitude = _ring_centroid(_largest_ring(feature["geometry"]))
        found[name] = (latitude, longitude)
    missing = [name for name in OFFICIAL if name not in found]
    if missing:
        raise RuntimeError(f"Boundary file is missing townships: {missing}")
    return found


def _known_points() -> list[tuple[str, float, float, float, float]]:
    """Name, weather lat/lon, discharge lat/lon from the river file and labeled table."""
    points: list[tuple[str, float, float, float, float]] = []
    if RIVER_POINTS.is_file():
        frame = pd.read_csv(RIVER_POINTS)
        for row in frame.itertuples(index=False):
            points.append(
                (
                    str(row.township),
                    float(row.weather_latitude),
                    float(row.weather_longitude),
                    float(row.river_latitude),
                    float(row.river_longitude),
                )
            )
    if VALIDATED.is_file():
        known = {name.casefold() for name, *_rest in points}
        daily = pd.read_csv(VALIDATED, usecols=["township", "lat", "lng"])
        grouped = daily.groupby("township", as_index=False).first()
        for row in grouped.itertuples(index=False):
            if str(row.township).casefold() in known:
                continue
            points.append((str(row.township), float(row.lat), float(row.lng), float(row.lat), float(row.lng)))
    return points


def _nearest(latitude: float, longitude: float, points: list[tuple[str, float, float, float, float]]) -> tuple[float, float]:
    def distance(point: tuple[str, float, float, float, float]) -> float:
        return (point[3] - latitude) ** 2 + (point[4] - longitude) ** 2

    chosen = min(points, key=distance)
    return chosen[3], chosen[4]


def _river_names() -> set[str]:
    if not RIVER_POINTS.is_file():
        return set()
    return {str(value).casefold() for value in pd.read_csv(RIVER_POINTS)["township"]}


def _place(
    name: str,
    weather_lat: float,
    weather_lon: float,
    river_lat: float,
    river_lon: float,
    *,
    official: bool,
) -> dict[str, object]:
    return {
        "township": name,
        "township_id": _slug(name),
        "latitude": weather_lat,
        "longitude": weather_lon,
        "discharge_latitude": river_lat,
        "discharge_longitude": river_lon,
        "official": official,
    }


def locations(end: date) -> list[dict[str, object]]:
    del end
    centers = _centroids()
    known = _known_points()
    known_by_name = {item[0].casefold(): item for item in known}
    river_names = _river_names()
    rows: list[dict[str, object]] = []
    for name in OFFICIAL:
        weather_lat, weather_lon = centers[name]
        stored = known_by_name.get(name.casefold())
        if name.casefold() in river_names and stored is not None:
            river_lat, river_lon = stored[3], stored[4]
        elif stored is not None:
            river_lat, river_lon = _nearest(weather_lat, weather_lon, known)
        else:
            river_lat, river_lon = _nearest(weather_lat, weather_lon, known)
        rows.append(_place(name, weather_lat, weather_lon, river_lat, river_lon, official=True))
    madauk = known_by_name.get("madauk")
    if madauk is not None:
        rows.append(_place("Madauk", madauk[1], madauk[2], madauk[3], madauk[4], official=False))
    return rows


class ArchiveDailyQuota(RuntimeError):
    """Open-Meteo archive rejected the call until the next UTC day."""


def _fetch(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "HydroFlow/2.0 (academic flood prototype)"})
    last_error: Exception | None = None
    for attempt in range(6):
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                payload = json.load(response)
            if not isinstance(payload, dict):
                raise RuntimeError("Open-Meteo did not return an object")
            return payload
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")[:300]
            last_error = RuntimeError(f"HTTP {exc.code}: {body}")
            if exc.code == 429 and "Daily API" in body:
                raise ArchiveDailyQuota(body) from exc
            if exc.code == 429:
                wait = 30 * 60
                print(f"  rate limit, waiting {wait // 60} minutes", flush=True)
                time.sleep(wait)
                continue
            if exc.code < 500:
                raise last_error from exc
            time.sleep(2 * (attempt + 1))
        except Exception as exc:  # noqa: BLE001 - retry transient network failures
            last_error = exc
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Request failed: {url.split('?', 1)[0]}") from last_error


def _cache_path(township_id: str, kind: str, start: date, end: date) -> Path:
    folder = CHUNK_DIR / township_id
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{kind}_{start.strftime('%Y%m%d')}_{end.strftime('%Y%m%d')}.json"


def _load_or_fetch(path: Path, url: str) -> dict:
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    payload = _fetch(url)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload), encoding="utf-8")
    temporary.replace(path)
    time.sleep(2.0)
    return payload


def _nasa_weather(township_id: str, latitude: float, longitude: float, start: date, end: date) -> pd.DataFrame:
    """Surface weather and soil wetness when the Open-Meteo archive quota is spent."""
    path = _cache_path(township_id, "nasa_power", start, end)
    query = urllib.parse.urlencode(
        {
            "parameters": "PRECTOTCORR,T2M,RH2M,WS2M,GWETTOP,GWETROOT",
            "community": "AG",
            "longitude": f"{longitude:.5f}",
            "latitude": f"{latitude:.5f}",
            "start": start.strftime("%Y%m%d"),
            "end": end.strftime("%Y%m%d"),
            "format": "JSON",
            "time-standard": "UTC",
        }
    )
    print(f"  nasa power {start} {end} {'cache' if path.is_file() else 'download'}", flush=True)
    payload = _load_or_fetch(path, f"https://power.larc.nasa.gov/api/temporal/daily/point?{query}")
    values = payload["properties"]["parameter"]
    days = sorted(values["PRECTOTCORR"])

    def series(name: str) -> list[float | None]:
        column: list[float | None] = []
        for day in days:
            raw = values[name].get(day)
            if raw is None or float(raw) <= -999:
                column.append(None)
            else:
                column.append(float(raw))
        return column

    return pd.DataFrame(
        {
            "date": pd.to_datetime(days, format="%Y%m%d"),
            "precipitation_mm": series("PRECTOTCORR"),
            "temperature_c": series("T2M"),
            "relative_humidity_pct": series("RH2M"),
            "wind_speed_m_s": series("WS2M"),
            "soil_moisture_0_to_7cm": series("GWETTOP"),
            "soil_moisture_7_to_28cm": series("GWETROOT"),
        }
    )


def _fill_et0(
    frame: pd.DataFrame,
    latitude: float,
    longitude: float,
    township_id: str,
    start: date,
    end: date,
) -> tuple[pd.DataFrame, str | None]:
    """Copy reference ET0 from the nearest township that already has an Open-Meteo series."""
    best_path: Path | None = None
    best_distance: float | None = None
    for path in MERGED_DIR.glob("*.csv"):
        if path.stem == township_id or not _already_complete(path, start, end):
            continue
        header = pd.read_csv(path, nrows=0).columns
        if "et0_fao_evapotranspiration" not in header or "latitude" not in header:
            continue
        sample = pd.read_csv(path, nrows=1)
        distance = (float(sample["latitude"].iloc[0]) - latitude) ** 2 + (
            float(sample["longitude"].iloc[0]) - longitude
        ) ** 2
        if best_distance is None or distance < best_distance:
            best_distance = distance
            best_path = path
    if best_path is None:
        frame = frame.copy()
        frame["et0_fao_evapotranspiration"] = pd.NA
        return frame, None
    donor = pd.read_csv(best_path, usecols=["date", "et0_fao_evapotranspiration"], parse_dates=["date"])
    merged = frame.merge(donor, on="date", how="left")
    print(f"  et0 filled from {best_path.stem}", flush=True)
    return merged, best_path.stem


def _weather_frame(township_id: str, latitude: float, longitude: float, start: date, end: date) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for chunk_start, chunk_end in _chunks(start, end):
        query = urllib.parse.urlencode(
            {
                "latitude": f"{latitude:.5f}",
                "longitude": f"{longitude:.5f}",
                "start_date": chunk_start.isoformat(),
                "end_date": chunk_end.isoformat(),
                "daily": WEATHER_DAILY,
                "timezone": "UTC",
                "wind_speed_unit": "ms",
            }
        )
        path = _cache_path(township_id, "weather", chunk_start, chunk_end)
        print(f"  weather {chunk_start} {chunk_end} {'cache' if path.is_file() else 'download'}", flush=True)
        payload = _load_or_fetch(path, f"{ARCHIVE_URL}?{query}")
        daily = payload["daily"]
        frames.append(
            pd.DataFrame(
                {
                    "date": pd.to_datetime(daily["time"]),
                    "precipitation_mm": daily["precipitation_sum"],
                    "temperature_c": daily["temperature_2m_mean"],
                    "relative_humidity_pct": daily["relative_humidity_2m_mean"],
                    "wind_speed_m_s": daily["wind_speed_10m_mean"],
                    "soil_moisture_0_to_7cm": daily["soil_moisture_0_to_7cm_mean"],
                    "soil_moisture_7_to_28cm": daily["soil_moisture_7_to_28cm_mean"],
                    "et0_fao_evapotranspiration": daily["et0_fao_evapotranspiration"],
                }
            )
        )
    return pd.concat(frames, ignore_index=True).drop_duplicates("date")


def _discharge_frame(township_id: str, latitude: float, longitude: float, start: date, end: date) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for chunk_start, chunk_end in _chunks(start, end):
        query = urllib.parse.urlencode(
            {
                "latitude": f"{latitude:.5f}",
                "longitude": f"{longitude:.5f}",
                "start_date": chunk_start.isoformat(),
                "end_date": chunk_end.isoformat(),
                "daily": "river_discharge",
                "forecast_days": 0,
            }
        )
        path = _cache_path(township_id, "discharge", chunk_start, chunk_end)
        print(f"  discharge {chunk_start} {chunk_end} {'cache' if path.is_file() else 'download'}", flush=True)
        payload = _load_or_fetch(path, f"{FLOOD_URL}?{query}")
        daily = payload["daily"]
        frame = pd.DataFrame(
            {
                "date": pd.to_datetime(daily["time"]),
                "river_discharge_m3s": daily["river_discharge"],
            }
        )
        if frame["river_discharge_m3s"].isna().all():
            legacy_query = urllib.parse.urlencode(
                {
                    "latitude": f"{latitude:.5f}",
                    "longitude": f"{longitude:.5f}",
                    "start_date": chunk_start.isoformat(),
                    "end_date": chunk_end.isoformat(),
                    "daily": "river_discharge",
                    "models": "consolidated_v4",
                    "forecast_days": 0,
                }
            )
            legacy_path = _cache_path(township_id, "discharge_consolidated", chunk_start, chunk_end)
            print(f"  discharge consolidated {chunk_start} {chunk_end}", flush=True)
            legacy = _load_or_fetch(legacy_path, f"{FLOOD_URL}?{legacy_query}")
            legacy_daily = legacy["daily"]
            frame = pd.DataFrame(
                {
                    "date": pd.to_datetime(legacy_daily["time"]),
                    "river_discharge_m3s": legacy_daily["river_discharge"],
                }
            )
        frames.append(frame)
    return pd.concat(frames, ignore_index=True).drop_duplicates("date")


def _already_complete(path: Path, start: date, end: date) -> bool:
    if not path.is_file():
        return False
    header = pd.read_csv(path, nrows=0).columns
    if any(column not in header for column in ("soil_moisture_0_to_7cm", "river_discharge_m3s", "date")):
        return False
    dates = pd.read_csv(path, usecols=["date"], parse_dates=["date"])["date"]
    if dates.empty:
        return False
    expected = (end - start).days + 1
    return dates.min().date() <= start and dates.max().date() >= end and len(dates) >= int(expected * 0.98)


def _write_merged(place: dict[str, object], start: date, end: date) -> Path:
    township_id = str(place["township_id"])
    destination = MERGED_DIR / f"{township_id}.csv"
    if _already_complete(destination, start, end):
        print(f"{township_id} already covers {start} to {end}", flush=True)
        return destination
    weather_source = "open-meteo-archive"
    et0_donor = None
    try:
        weather = _weather_frame(township_id, float(place["latitude"]), float(place["longitude"]), start, end)
    except ArchiveDailyQuota:
        print("  Open-Meteo daily quota reached; NASA POWER supplies weather and soil wetness", flush=True)
        weather = _nasa_weather(township_id, float(place["latitude"]), float(place["longitude"]), start, end)
        weather, et0_donor = _fill_et0(
            weather,
            float(place["latitude"]),
            float(place["longitude"]),
            township_id,
            start,
            end,
        )
        weather_source = "nasa-power"
    discharge = _discharge_frame(
        township_id,
        float(place["discharge_latitude"]),
        float(place["discharge_longitude"]),
        start,
        end,
    )
    frame = weather.merge(discharge, on="date", how="left")
    frame["rainfall_mm"] = frame["precipitation_mm"]
    frame["township_id"] = township_id
    frame["township"] = place["township"]
    frame["latitude"] = place["latitude"]
    frame["longitude"] = place["longitude"]
    frame["discharge_latitude"] = place["discharge_latitude"]
    frame["discharge_longitude"] = place["discharge_longitude"]
    frame["weather_source"] = weather_source
    frame["et0_donor"] = et0_donor
    frame = frame.sort_values("date")
    MERGED_DIR.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".csv.tmp")
    frame.loc[:, list(MERGED_COLUMNS)].to_csv(temporary, index=False, date_format="%Y-%m-%d")
    temporary.replace(destination)
    print(
        f"{township_id} wrote {len(frame)} days {frame['date'].min().date()} {frame['date'].max().date()}",
        flush=True,
    )
    return destination


def main() -> None:
    end = _yesterday()
    places = locations(end)
    manifest = ROOT / "data" / "external" / "bago28_locations.json"
    log_path = ROOT / "data" / "external" / "bago28_download.log"
    manifest.write_text(json.dumps(places, indent=2), encoding="utf-8")
    print(f"locations {len(places)} {HISTORY_START} {end}", flush=True)
    failures: list[str] = []
    for place in places:
        print(f"{place['township_id']} weather={place['latitude']:.3f},{place['longitude']:.3f}", flush=True)
        try:
            _write_merged(place, HISTORY_START, end)
        except Exception as exc:
            failures.append(str(place["township_id"]))
            message = f"{place['township_id']} failed: {exc}\n{traceback.format_exc()}"
            print(message, flush=True)
            with log_path.open("a", encoding="utf-8") as handle:
                handle.write(message + "\n")
    official = [place["township_id"] for place in places if place["official"]]
    if len(official) != 28:
        raise RuntimeError(f"Expected 28 official townships, found {len(official)}")
    if failures:
        raise RuntimeError(f"Download failed for: {', '.join(failures)}")


if __name__ == "__main__":
    main()
