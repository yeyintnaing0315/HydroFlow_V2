"""Persist Bago township flood forecasts for today and the next three days.

Static hazard is the centroid distance to ``bago_river_points.csv``. Open-Meteo
and GloFAS values used for a score are written to the hydro feature cache.
The served histogram-gradient-boosting model is not retrained here.
"""

from __future__ import annotations

import asyncio
import math
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any

import pandas as pd
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.cache.hydro_features import EngineeredFeature, feature_engine
from app.models import FloodLabel, PredictionRun, TownshipForecast, TownshipStaticFeatures
from app.services import admin_areas, live_features, prediction
from app.services.geography import GeographyUnavailableError
from app.services.open_admin_areas import bundled_bago_areas
from app.services.risk import band_to_risk_level, flood_probability_band, horizon_probability

ACADEMIC_DISCLAIMER = (
    "Flood probabilities are uncalibrated academic model scores. "
    "Recorded impacts are validated relief labels, not model outputs."
)
LEAD_DAYS = (0, 1, 2, 3)
HORIZON_LAST_DAY = 7
INCOMPLETE_RETRY = timedelta(minutes=15)
REQUEST_BUDGET_SECONDS = 16.0
_NAME_ALIASES = {"okpho": "okpo", "phyu": "pyu", "paukkhaung": "paukkaung"}
_BAND_RANK = {"low": 0, "moderate": 1, "high": 2, "very_high": 3}


class FloodDrivers(BaseModel):
    rain: str
    discharge: str
    floodplain_or_river_distance: str


class RegionForecastScore(BaseModel):
    township_id: str
    township_name: str
    district_id: str
    latitude: float | None = None
    longitude: float | None = None
    lead_days: int
    target_date: date
    flood_probability: float | None = Field(default=None, ge=0, le=1)
    risk_band: str
    probability_risk_level: str | None = None
    risk_level: str
    rainfall_mm: float | None = None
    horizon_3d: float | None = Field(default=None, ge=0, le=1)
    horizon_7d: float | None = Field(default=None, ge=0, le=1)
    discharge_m3_s: float | None = None
    static_hazard: float | None = None
    early_warning: bool
    warning_reason: str | None = None
    warning_level: str | None = None
    drivers: FloodDrivers
    data_status: str


class RegionForecastResponse(BaseModel):
    as_of: date
    run_id: int | None = None
    model_version: str
    feature_version: str
    disclaimer: str
    cached: bool
    labels_found: bool
    label_file: str | None = None
    missing_inputs: list[str]
    scores: list[RegionForecastScore]


def early_warning_reason(
    bands: list[str],
    discharges: list[float | None],
    p95: float | None,
) -> tuple[bool, str | None, str | None]:
    """Warning when a band reaches high or very high within three days, or discharge exceeds p95."""
    reasons: list[str] = []
    warning_level: str | None = None
    ranked = [(index, band) for index, band in enumerate(bands) if band in _BAND_RANK]
    high_days = [(index, band) for index, band in ranked if _BAND_RANK[band] >= 2]
    if high_days:
        lead, band = high_days[0]
        label = "very high" if band == "very_high" else "high"
        if lead == 0:
            reasons.append(f"Band is {label} within the three-day outlook.")
        else:
            reasons.append(f"Band rises into {label} by day +{lead}.")
        warning_level = "severe" if any(item[1] == "very_high" for item in high_days) else "high"
    exceeded = False
    if p95 is not None:
        for index, value in enumerate(discharges):
            if value is not None and float(value) > float(p95):
                exceeded = True
                reasons.append(
                    f"Forecast discharge {float(value):.1f} m³/s on day +{index} "
                    f"exceeds the historical 95th percentile {float(p95):.1f} m³/s."
                )
                break
    if exceeded and warning_level is None:
        warning_level = "high"
    if not reasons:
        return False, None, None
    return True, " ".join(reasons), warning_level


def _norm(value: str) -> str:
    compact = "".join(character for character in value.casefold() if character.isalnum())
    return _NAME_ALIASES.get(compact, compact)


def _feature_version() -> str:
    return str(live_features._static_prior().FEATURE_VERSION)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _areas_payload(session: Session) -> dict[str, Any]:
    try:
        return admin_areas.bago_areas(session)
    except GeographyUnavailableError:
        return bundled_bago_areas()


def _townships(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for district in payload.get("districts") or []:
        for township in district.get("townships") or []:
            if township.get("latitude") is None or township.get("longitude") is None:
                continue
            rows.append(
                {
                    "id": str(township["id"]),
                    "name_en": str(township.get("name_en") or township["id"]),
                    "latitude": float(township["latitude"]),
                    "longitude": float(township["longitude"]),
                    "district_id": str(district.get("id") or ""),
                    "district_name": str(district.get("name_en") or ""),
                    "geometry": township.get("geometry") if isinstance(township.get("geometry"), dict) else None,
                }
            )
    return rows


def _percentile_95(values: list[float]) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(0.95 * len(ordered)) - 1))
    return float(ordered[index])


def _consider_series(
    table: dict[str, dict[str, Any]],
    key: str,
    values: list[float],
    source: str,
) -> None:
    clean = [float(value) for value in values if value is not None and not math.isnan(float(value))]
    if len(clean) < 20:
        return
    current = table.get(key)
    if current is not None and int(current["n"]) >= len(clean):
        return
    table[key] = {"p95": _percentile_95(clean), "n": len(clean), "source": source}


def discharge_percentiles() -> dict[str, dict[str, Any]]:
    """Historical discharge p95 from the relief file, then local GloFAS extracts."""
    table: dict[str, dict[str, Any]] = {}
    module = live_features._static_prior()
    label_path = module.discover_label_path()
    if label_path is not None:
        frame = pd.read_csv(label_path, usecols=["township_id", "township", "river_discharge_m3s"])
        for (township_id, township), group in frame.groupby(["township_id", "township"], dropna=False):
            values = [float(value) for value in group["river_discharge_m3s"].dropna().tolist()]
            source = label_path.name
            _consider_series(table, _norm(str(township_id)), values, source)
            _consider_series(table, _norm(str(township)), values, source)
    glofas_dir = module.project_root() / "data" / "external" / "glofas_discharge"
    if glofas_dir.is_dir():
        for path in sorted(glofas_dir.glob("*.csv")):
            try:
                frame = pd.read_csv(path, usecols=["river_discharge_m3s"])
            except (OSError, ValueError):
                continue
            values = [float(value) for value in frame["river_discharge_m3s"].dropna().tolist()]
            stem = path.stem
            _consider_series(table, _norm(stem), values, path.name)
            head = stem.split("-", 1)[0]
            _consider_series(table, _norm(head), values, path.name)
    return table


def _p95_for(township: dict[str, Any], table: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    for raw in (township["id"], township["name_en"]):
        found = table.get(_norm(str(raw)))
        if found is not None:
            return found
    return None


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        if math.isnan(float(value)):
            return None
    except (TypeError, ValueError):
        return None
    return int(value)


def import_flood_labels(session: Session, townships: list[dict[str, Any]]) -> Path | None:
    """Copy observed flood days into flood_labels. Non-flood days are not invented."""
    module = live_features._static_prior()
    path = module.discover_label_path()
    if path is None:
        return None
    by_name = {_norm(item["name_en"]): item["id"] for item in townships}
    by_name.update({_norm(item["id"]): item["id"] for item in townships})
    frame = pd.read_csv(
        path,
        usecols=["date", "township_id", "township", "affected_people", "flood"],
        parse_dates=["date"],
    )
    # Only days the relief file marks as flood. Unlabeled years stay absent.
    floods = frame.loc[frame["flood"].fillna(0).astype(int) == 1]
    existing = {
        (row[0], row[1])
        for row in session.execute(select(FloodLabel.township_id, FloodLabel.observed_date)).all()
    }
    for item in floods.itertuples(index=False):
        try:
            if int(item.flood) != 1:
                continue
        except (TypeError, ValueError):
            continue
        township_id = (
            by_name.get(_norm(str(item.township)))
            or by_name.get(_norm(str(item.township_id)))
            or str(item.township_id)
        )
        observed = item.date.date() if hasattr(item.date, "date") else item.date
        key = (township_id, observed)
        if key in existing:
            continue
        session.add(
            FloodLabel(
                township_id=township_id,
                observed_date=observed,
                observed=True,
                affected_people=_optional_int(item.affected_people),
                source=path.name,
            )
        )
        existing.add(key)
    return path


def ensure_static_features(session: Session, townships: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """One current static-hazard row per township. Raster gaps stay null and are listed."""
    module = live_features._static_prior()
    rivers = module.load_river_points(live_features.RIVER_POINTS_CSV)
    missing = list(module.missing_raster_inputs())
    version = _feature_version()
    stored: dict[str, dict[str, Any]] = {}
    for township in townships:
        distance = module.centroid_river_distance_km(township["latitude"], township["longitude"], rivers)
        boundary = module.boundary_river_distance_km(township.get("geometry"), rivers)
        hazard = module.hazard_from_distance_km(distance)
        river = module.nearest_river(township["latitude"], township["longitude"], rivers)
        spec = module.upstream_spec(township["latitude"], township["longitude"], rivers)
        population = _population(township["name_en"])
        payload = {
            "river_distance_km": distance,
            "boundary_river_distance_km": boundary,
            "nearest_river_township": None if river is None else river["township"],
            "nearest_river_code": None if river is None else river["code"],
            "prior_method": "centroid distance to bago_river_points.csv",
            "missing_inputs": missing,
            "inputs_present": [
                "bago_township_boundaries.geojson" if township.get("geometry") else "township centroid",
                "bago_river_points.csv" if rivers else None,
            ],
            "population_total": population,
            "upstream_mode": spec["mode"],
            "upstream_points": spec["points"],
            "upstream_note": spec["note"],
            "basin_note": "Local district grouping. HydroBASINS polygons are not on disk.",
        }
        payload["inputs_present"] = [item for item in payload["inputs_present"] if item]
        row = session.scalar(
            select(TownshipStaticFeatures).where(TownshipStaticFeatures.township_id == township["id"])
        )
        if row is None:
            row = TownshipStaticFeatures(
                township_id=township["id"],
                feature_version=version,
                features=payload,
            )
            session.add(row)
        row.hand_m = None
        row.jrc_rp10_depth_m = None
        row.jrc_rp50_depth_m = None
        row.jrc_rp100_depth_m = None
        row.jrc_rp10_percent = None
        row.jrc_rp50_percent = None
        row.jrc_rp100_percent = None
        row.landcover_water_share = None
        row.landcover_wetland_share = None
        row.landcover_cropland_share = None
        row.landcover_builtup_share = None
        row.basin_id = module.basin_id(township["district_name"], township["longitude"])
        row.feature_version = version
        row.features = payload
        stored[township["id"]] = {
            **payload,
            "static_hazard": hazard,
            "basin_id": row.basin_id,
            "upstream_spec": spec,
        }
    session.flush()
    return stored


def _population(name_en: str) -> int | None:
    try:
        from app.services import census

        profile = census.township_profile(name_en)
    except Exception:
        return None
    if profile is None:
        return None
    _district, township = profile
    return int(township.population.total)


def _matching_run(
    session: Session,
    as_of: date,
    model_version: str,
    feature_version: str,
    expected_rows: int,
) -> tuple[PredictionRun | None, bool]:
    runs = session.scalars(
        select(PredictionRun)
        .where(
            PredictionRun.as_of == as_of,
            PredictionRun.model_version == model_version,
            PredictionRun.feature_version == feature_version,
            PredictionRun.status.in_(("ready", "incomplete")),
        )
        .order_by(PredictionRun.id.desc())
    ).all()
    now = datetime.now(timezone.utc)
    for run in runs:
        count = session.scalar(
            select(func.count()).select_from(TownshipForecast).where(TownshipForecast.run_id == run.id)
        )
        if not count or int(count) < expected_rows:
            continue
        if run.status == "incomplete" and now - _aware(run.created_at) >= INCOMPLETE_RETRY:
            continue
        if run.status == "ready":
            unknown = session.scalar(
                select(func.count())
                .select_from(TownshipForecast)
                .where(
                    TownshipForecast.run_id == run.id,
                    TownshipForecast.risk_band == "unknown",
                )
            )
            # Older runs were marked ready after the request budget skipped the
            # remaining townships. Rebuild those instead of serving the gap.
            if unknown:
                continue
        sample = session.scalar(
            select(TownshipForecast).where(
                TownshipForecast.run_id == run.id,
                TownshipForecast.lead_days == 0,
            )
        )
        sample_features = sample.features if sample is not None and isinstance(sample.features, dict) else {}
        if "horizon_3d" not in sample_features:
            continue
        return run, True
    return None, False


def _read_cached_row(township_id: str, day: date, feature_version: str) -> dict[str, Any] | None:
    with Session(feature_engine()) as cache:
        row = cache.scalar(
            select(EngineeredFeature).where(
                EngineeredFeature.township_id == township_id,
                EngineeredFeature.observed_on == day,
                EngineeredFeature.feature_version == feature_version,
            )
        )
        if row is None or not isinstance(row.payload, dict):
            return None
        payload = dict(row.payload)
        payload["date"] = day
        return payload


def _local_feature_map(
    township: dict[str, Any],
    as_of: date,
    feature_version: str,
) -> dict[date, dict[str, Any]]:
    """Score inputs from on-disk hydrology. This path does not make HTTP calls."""
    start = as_of - timedelta(days=live_features.CONTEXT_DAYS)
    end = as_of + timedelta(days=HORIZON_LAST_DAY)
    by_date: dict[date, dict[str, Any]] = {}
    try:
        observations = live_features.offline_observations(
            township["id"],
            township["latitude"],
            township["longitude"],
            start,
            end,
            catalog_township_id=township["id"],
        )
        rows = live_features.features_on_or_after(
            observations,
            start,
            township["id"],
            township["latitude"],
            township["longitude"],
        )
        by_date = {row["date"]: row for row in rows if isinstance(row.get("date"), date)}
    except Exception:
        by_date = {}
    for lead in range(HORIZON_LAST_DAY + 1):
        day = as_of + timedelta(days=lead)
        if day not in by_date:
            cached = _read_cached_row(township["id"], day, feature_version)
            if cached is not None:
                by_date[day] = cached
    return by_date


def _lead_days_missing(by_date: dict[date, dict[str, Any]], as_of: date) -> bool:
    return any(as_of + timedelta(days=lead) not in by_date for lead in LEAD_DAYS)


async def _observation_rows(
    township: dict[str, Any],
    as_of: date,
    feature_version: str,
) -> dict[date, dict[str, Any]]:
    start = as_of - timedelta(days=live_features.CONTEXT_DAYS)
    end = as_of + timedelta(days=HORIZON_LAST_DAY)
    rows: list[dict[str, Any]] = []
    try:
        observations = await live_features.observations_for_timeline(
            township["id"],
            township["latitude"],
            township["longitude"],
            start,
            end,
            catalog_township_id=township["id"],
        )
        rows = live_features.features_on_or_after(
            observations,
            start,
            township["id"],
            township["latitude"],
            township["longitude"],
        )
    except Exception:
        rows = []
    by_date = {row["date"]: row for row in rows if isinstance(row.get("date"), date)}
    for lead in range(HORIZON_LAST_DAY + 1):
        day = as_of + timedelta(days=lead)
        if day not in by_date:
            cached = _read_cached_row(township["id"], day, feature_version)
            if cached is not None:
                by_date[day] = cached
    return by_date


def _apply_upstream(
    row: dict[str, Any],
    spec: dict[str, Any],
    daily_mm: dict[date, float],
    fetch_failed: bool,
) -> None:
    day = row.get("date")
    if (
        spec.get("mode") == "upstream_river_proxy"
        and isinstance(day, date)
        and day in daily_mm
        and not fetch_failed
    ):
        row["rainfall_upstream_1d_mm"] = float(daily_mm[day])
        row["rainfall_upstream_mode"] = "upstream_river_proxy"
        row["rainfall_upstream_note"] = spec.get("note")
        return
    row["rainfall_upstream_1d_mm"] = row.get("rainfall_upstream_1d_mm", row.get("rainfall_1d_mm"))
    row["rainfall_upstream_mode"] = "centroid_only_fallback"
    if spec.get("mode") == "upstream_river_proxy":
        row["rainfall_upstream_note"] = (
            "Upstream river-proxy coordinates exist, but Open-Meteo rainfall was "
            "unavailable. Rainfall features use the township centroid only."
        )
    else:
        row["rainfall_upstream_note"] = spec.get("note")


def _drivers(row: dict[str, Any] | None, static_row: dict[str, Any]) -> FloodDrivers:
    if row is None or row.get("rainfall_mm") is None:
        rain = "Rainfall unavailable"
    else:
        rain = f"Rainfall {float(row['rainfall_mm']):.1f} mm"
        if row.get("rainfall_7d_mm") is not None:
            rain += f"; 7-day {float(row['rainfall_7d_mm']):.1f} mm"
        if row.get("rainfall_upstream_mode") == "upstream_river_proxy" and row.get("rainfall_upstream_1d_mm") is not None:
            rain += f"; upstream basin {float(row['rainfall_upstream_1d_mm']):.1f} mm"
        elif row.get("rainfall_upstream_mode") == "centroid_only_fallback":
            rain += "; centroid-only rainfall"
    if row is None or row.get("river_discharge_m3s") is None:
        discharge = "Discharge unavailable"
    else:
        discharge = f"Discharge {float(row['river_discharge_m3s']):.1f} m³/s"
    distance = static_row.get("river_distance_km")
    if distance is None:
        floodplain = "River-distance prior unavailable"
    else:
        floodplain = f"River-distance prior {float(distance):.1f} km from the centroid to the nearest river proxy"
        boundary = static_row.get("boundary_river_distance_km")
        if boundary is not None:
            floodplain += f"; nearest polygon sample {float(boundary):.1f} km"
    if static_row.get("missing_inputs"):
        floodplain += ". JRC floodplain raster missing"
    return FloodDrivers(rain=rain, discharge=discharge, floodplain_or_river_distance=floodplain)


async def _upstream_tables(
    townships: list[dict[str, Any]],
    static_rows: dict[str, dict[str, Any]],
) -> dict[str, tuple[dict[date, float], bool]]:
    """Use centroid rainfall on the request path.

    Upstream Open-Meteo calls are not made here. A missing upstream series is the
    documented centroid-only fallback, which still leaves the model features scorable.
    """
    del static_rows
    return {township["id"]: ({}, False) for township in townships}


def _json_features(payload: dict[str, Any]) -> dict[str, Any]:
    plain: dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(value, (date, datetime)):
            plain[key] = value.isoformat()
        elif isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            plain[key] = None
        elif isinstance(value, (str, int, float, bool)) or value is None:
            plain[key] = value
        elif isinstance(value, dict):
            plain[key] = _json_features(value)
        elif isinstance(value, list):
            plain[key] = [
                item if isinstance(item, (str, int, float, bool)) or item is None else str(item)
                for item in value
            ]
        else:
            plain[key] = str(value)
    return plain


async def build_region_forecast(session: Session, as_of: date) -> RegionForecastResponse:
    """Score every Bago township for as_of and lead days +1, +2, and +3."""
    _model, metadata = prediction.load_model()
    model_version = prediction.model_version_name(metadata)
    feature_version = _feature_version()
    townships = _townships(_areas_payload(session))
    if not townships:
        raise ValueError("No Bago townships are available to score")
    expected = len(townships) * len(LEAD_DAYS)
    existing, cached = _matching_run(session, as_of, model_version, feature_version, expected)
    if existing is not None and cached:
        return _response_from_run(session, existing, as_of, cached=True)

    static_rows = ensure_static_features(session, townships)
    import_flood_labels(session, townships)
    session.commit()
    percentiles = discharge_percentiles()
    started = time.monotonic()
    with live_features.external_budget(REQUEST_BUDGET_SECONDS):
        upstream = await _upstream_tables(townships, static_rows)
        semaphore = asyncio.Semaphore(4)
        loaded: dict[str, dict[date, dict[str, Any]]] = {}

        async def _load(township: dict[str, Any]) -> None:
            await asyncio.sleep(0)
            # Local files cover every township. Do this outside the HTTP budget so
            # Pyay, Nattalin, and Thayarwady are not dropped after the eastern districts.
            local = _local_feature_map(township, as_of, feature_version)
            if _lead_days_missing(local, as_of):
                remaining = REQUEST_BUDGET_SECONDS - (time.monotonic() - started)
                if remaining > 0.05:
                    async with semaphore:
                        remaining = REQUEST_BUDGET_SECONDS - (time.monotonic() - started)
                        if remaining > 0.05:
                            try:
                                extra = await asyncio.wait_for(
                                    _observation_rows(township, as_of, feature_version),
                                    timeout=remaining,
                                )
                            except (TimeoutError, asyncio.TimeoutError):
                                extra = {}
                            for day, row in extra.items():
                                local.setdefault(day, row)
            loaded[township["id"]] = local

        await asyncio.gather(*[_load(township) for township in townships])
    prepared_rows: list[dict[str, Any] | None] = []
    for township in townships:
        daily_mm, fetch_failed = upstream.get(township["id"], ({}, False))
        spec = static_rows[township["id"]]["upstream_spec"]
        by_date = loaded.get(township["id"], {})
        for lead in range(HORIZON_LAST_DAY + 1):
            target = as_of + timedelta(days=lead)
            row = by_date.get(target)
            if row is not None:
                _apply_upstream(row, spec, daily_mm, fetch_failed)
            prepared_rows.append(row)
    batched_probabilities = prediction.predict_probabilities(prepared_rows)
    prepared: list[dict[str, Any]] = []
    row_index = 0
    for township in townships:
        horizon_probabilities: list[float | None] = []
        day_results: list[dict[str, Any]] = []
        for lead in range(HORIZON_LAST_DAY + 1):
            target = as_of + timedelta(days=lead)
            row = prepared_rows[row_index]
            probability = batched_probabilities[row_index]
            row_index += 1
            horizon_probabilities.append(probability)
            if lead not in LEAD_DAYS:
                continue
            status = "model_estimate" if probability is not None else "unavailable"
            day_results.append(
                {
                    "lead": lead,
                    "target": target,
                    "row": row,
                    "probability": probability,
                    "status": status,
                }
            )
        horizon_3d = horizon_probability(horizon_probabilities[:4])
        horizon_7d = horizon_probability(horizon_probabilities)
        history = _p95_for(township, percentiles)
        p95 = None if history is None else float(history["p95"])
        warning, reason, warning_level = early_warning_reason(
            [
                flood_probability_band(float(item["probability"]))
                if item["status"] == "model_estimate" and item["probability"] is not None
                else "unknown"
                for item in day_results
            ],
            [
                None
                if item["row"] is None or item["row"].get("river_discharge_m3s") is None
                else float(item["row"]["river_discharge_m3s"])
                for item in day_results
            ],
            p95,
        )
        for item in day_results:
            item["warning"] = warning
            item["reason"] = reason
            item["warning_level"] = warning_level
            item["p95"] = history
            item["horizon_3d"] = horizon_3d
            item["horizon_7d"] = horizon_7d
        prepared.append({"township": township, "days": day_results})

    fully_scored = bool(prepared) and all(
        day["status"] == "model_estimate" for item in prepared for day in item["days"]
    )
    run = PredictionRun(
        as_of=as_of,
        model_version=model_version,
        feature_version=feature_version,
        status="ready" if fully_scored else "incomplete",
        created_at=datetime.now(timezone.utc),
    )
    session.add(run)
    session.flush()
    for item in prepared:
        township = item["township"]
        static_row = static_rows[township["id"]]
        for day in item["days"]:
            row = day["row"]
            status = str(day["status"])
            probability = day["probability"]
            band = (
                flood_probability_band(float(probability))
                if status == "model_estimate" and probability is not None
                else "unknown"
            )
            drivers = _drivers(row, static_row)
            session.add(
                TownshipForecast(
                    run_id=run.id,
                    township_id=township["id"],
                    target_date=day["target"],
                    lead_days=int(day["lead"]),
                    probability=float(probability) if probability is not None else 0.0,
                    risk_band=band,
                    rainfall_mm=None if row is None or row.get("rainfall_mm") is None else float(row["rainfall_mm"]),
                    discharge_m3_s=(
                        None
                        if row is None or row.get("river_discharge_m3s") is None
                        else float(row["river_discharge_m3s"])
                    ),
                    static_hazard=static_row.get("static_hazard"),
                    warning_reason=day["reason"],
                    feature_version=feature_version,
                    features=_json_features(
                        {
                            "township_name": township["name_en"],
                            "district_id": township["district_id"],
                            "latitude": township["latitude"],
                            "longitude": township["longitude"],
                            "data_status": status,
                            "early_warning": bool(day["warning"]),
                            "warning_level": day["warning_level"],
                            "drivers": drivers.model_dump(),
                            "rainfall_upstream_mode": None if row is None else row.get("rainfall_upstream_mode"),
                            "rainfall_upstream_note": None if row is None else row.get("rainfall_upstream_note"),
                            "discharge_p95": None if day["p95"] is None else day["p95"]["p95"],
                            "discharge_p95_days": None if day["p95"] is None else day["p95"]["n"],
                            "discharge_p95_source": None if day["p95"] is None else day["p95"]["source"],
                            "missing_inputs": static_row.get("missing_inputs") or [],
                            "basin_id": static_row.get("basin_id"),
                            "horizon_3d": day.get("horizon_3d"),
                            "horizon_7d": day.get("horizon_7d"),
                        }
                    ),
                )
            )
    session.commit()
    return _response_from_run(session, run, as_of, cached=False)


def _labels_meta() -> tuple[bool, str | None]:
    path = live_features._static_prior().discover_label_path()
    if path is None:
        return False, None
    return True, path.name


def _missing_inputs(session: Session) -> list[str]:
    row = session.scalar(select(TownshipStaticFeatures).limit(1))
    if row is None or not isinstance(row.features, dict):
        return []
    raw = row.features.get("missing_inputs") or []
    return [str(item) for item in raw]


def _response_from_run(
    session: Session,
    run: PredictionRun,
    as_of: date,
    *,
    cached: bool,
    lead_days: int | None = None,
    district_id: str | None = None,
) -> RegionForecastResponse:
    rows = session.scalars(
        select(TownshipForecast)
        .where(TownshipForecast.run_id == run.id)
        .order_by(TownshipForecast.township_id, TownshipForecast.lead_days)
    ).all()
    labels_found, label_file = _labels_meta()
    grouped: dict[str, list[TownshipForecast]] = {}
    for row in rows:
        grouped.setdefault(row.township_id, []).append(row)
    township_horizons: dict[str, tuple[float | None, float | None]] = {}
    for township_id, group in grouped.items():
        stored = next(
            (
                item.features
                for item in group
                if isinstance(item.features, dict) and "horizon_3d" in item.features
            ),
            None,
        )
        if isinstance(stored, dict):
            township_horizons[township_id] = (
                None if stored.get("horizon_3d") is None else float(stored["horizon_3d"]),
                None if stored.get("horizon_7d") is None else float(stored["horizon_7d"]),
            )
            continue
        daily: list[float | None] = []
        for lead in LEAD_DAYS:
            match = next((item for item in group if int(item.lead_days) == lead), None)
            if match is None:
                daily.append(None)
                continue
            features = match.features if isinstance(match.features, dict) else {}
            status = str(features.get("data_status") or "model_estimate")
            daily.append(None if status != "model_estimate" else float(match.probability))
        township_horizons[township_id] = (horizon_probability(daily), None)
    scores: list[RegionForecastScore] = []
    for row in rows:
        payload = row.features if isinstance(row.features, dict) else {}
        if lead_days is not None and int(row.lead_days) != lead_days:
            continue
        row_district = str(payload.get("district_id") or "")
        if district_id and row_district != district_id:
            continue
        status = str(payload.get("data_status") or "model_estimate")
        drivers_raw = payload.get("drivers") if isinstance(payload.get("drivers"), dict) else {}
        drivers = FloodDrivers(
            rain=str(drivers_raw.get("rain") or "Rainfall unavailable"),
            discharge=str(drivers_raw.get("discharge") or "Discharge unavailable"),
            floodplain_or_river_distance=str(
                drivers_raw.get("floodplain_or_river_distance") or "River-distance prior unavailable"
            ),
        )
        band = str(row.risk_band)
        level = None if band == "unknown" else band_to_risk_level(band)
        horizon_3d, horizon_7d = township_horizons.get(row.township_id, (None, None))
        scores.append(
            RegionForecastScore(
                township_id=row.township_id,
                township_name=str(payload.get("township_name") or row.township_id),
                district_id=row_district,
                latitude=payload.get("latitude"),
                longitude=payload.get("longitude"),
                lead_days=int(row.lead_days),
                target_date=row.target_date,
                flood_probability=None if status != "model_estimate" else float(row.probability),
                risk_band=band,
                probability_risk_level=level,
                risk_level=level or "unknown",
                rainfall_mm=row.rainfall_mm,
                horizon_3d=horizon_3d,
                horizon_7d=horizon_7d,
                discharge_m3_s=row.discharge_m3_s,
                static_hazard=row.static_hazard,
                early_warning=bool(payload.get("early_warning")),
                warning_reason=row.warning_reason,
                warning_level=payload.get("warning_level"),
                drivers=drivers,
                data_status=status,
            )
        )
    return RegionForecastResponse(
        as_of=as_of,
        run_id=run.id,
        model_version=run.model_version,
        feature_version=run.feature_version,
        disclaimer=ACADEMIC_DISCLAIMER,
        cached=cached,
        labels_found=labels_found,
        label_file=label_file,
        missing_inputs=_missing_inputs(session),
        scores=scores,
    )


def region_forecast(
    session: Session,
    run: PredictionRun,
    *,
    lead_days: int | None = None,
    district_id: str | None = None,
) -> RegionForecastResponse:
    return _response_from_run(
        session,
        run,
        run.as_of,
        cached=True,
        lead_days=lead_days,
        district_id=district_id,
    )
