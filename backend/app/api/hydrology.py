import asyncio
from datetime import date, datetime, time, timezone
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.api import (
    AlertCreate,
    AlertResponse,
    BagoAreasResponse,
    FloodCaseCatalogResponse,
    FloodHistoryResponse,
    ForecastPoint,
    ForecastResponse,
    HelpBriefResponse,
    HelpDay,
    HelpResponse,
    HistoricalResponse,
    OutlookResponse,
    PredictRequest,
    PredictResponse,
    RiskResponse,
    RoutePlanRequest,
    RoutePlanResponse,
    TopographyResponse,
    TownshipResponse,
)
from app.services import (
    admin_areas,
    clients,
    flood_cases,
    flood_history,
    help_prediction,
    kardinal,
    live_features,
    open_admin_areas,
    persistence,
    prediction,
)
from app.services.census import CensusUnavailableError, load_census
from app.services.geography import GeographyUnavailableError
from app.services.risk import academic_risk_score

router = APIRouter()


def _merge_forecast_points(*groups: list[ForecastPoint]) -> list[ForecastPoint]:
    """Combine weather and discharge rows that share a timestamp into one point."""
    merged: dict[datetime, ForecastPoint] = {}
    order: list[datetime] = []
    fields = (
        "precipitation_mm",
        "temperature_c",
        "relative_humidity_pct",
        "wind_speed_m_s",
        "discharge_m3_s",
    )
    for group in groups:
        for point in group:
            current = merged.get(point.timestamp)
            if current is None:
                merged[point.timestamp] = point
                order.append(point.timestamp)
                continue
            update = {
                name: value
                for name in fields
                if (value := getattr(point, name)) is not None
            }
            merged[point.timestamp] = current.model_copy(update=update)
    return [merged[stamp] for stamp in order]


def _ensure_model() -> None:
    try:
        prediction.load_model()
    except prediction.ModelUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _record_alert(session: Session, data: PredictRequest, day: date, level: str) -> bool:
    if level not in {"high", "severe"}:
        return False
    location = persistence.get_or_create_location(
        session, data.township_id, data.latitude, data.longitude
    )
    persistence.add_alert(
        session,
        AlertCreate(
            location_id=location.id,
            issued_at=datetime.combine(day, time.min, tzinfo=timezone.utc),
            level=level,
            message=(
                f"Academic prototype only: {data.township_id} on {day.isoformat()} "
                f"is {level} using Open-Meteo and GloFAS. Not an operational warning."
            ),
        ),
    )
    return True


def _feature_payload(row: dict) -> dict:
    return {key: value for key, value in row.items() if key != "date"}


def _outlook_uncertainty(in_training_set: bool) -> str:
    if in_training_set:
        return (
            "Uncalibrated academic score for flood in the next 3 days. "
            "Live rainfall is Open-Meteo, not CHIRPS. Not an official warning."
        )
    return (
        "This township is outside the 14 close-river training set. "
        "The score is an out-of-sample academic estimate, not an official warning."
    )


async def _api_feature_rows(data: PredictRequest) -> list[dict]:
    try:
        observations = await live_features.load_observations(data.latitude, data.longitude)
        return live_features.features_on_or_after(
            observations,
            data.date,
            data.township_id,
            data.latitude,
            data.longitude,
        )
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=f"Forecast provider error: {exc}") from exc


@router.post("/predict", response_model=PredictResponse, tags=["prediction"])
async def create_prediction(
    data: PredictRequest, session: Session = Depends(get_db)
) -> PredictResponse:
    _ensure_model()
    rows = await _api_feature_rows(data)
    row = next((item for item in rows if item["date"] == data.date), None)
    if row is None:
        from app.services.hydro_history import APP_HISTORY_START
        from app.services.hydro_offline_db import hydrology_error_message

        raise HTTPException(
            status_code=422,
            detail=hydrology_error_message(
                window_start=data.date,
                window_end=data.date,
                operational_start=APP_HISTORY_START,
            ),
        )
    try:
        probability, predicted_flood, threshold, version = prediction.predict(_feature_payload(row))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return PredictResponse(
        flood_probability=probability,
        predicted_flood=bool(predicted_flood),
        threshold=threshold,
        model_version=version,
        alert_recorded=False,
    )


@router.post("/outlook", response_model=OutlookResponse, tags=["prediction"])
async def create_outlook(
    data: PredictRequest, session: Session = Depends(get_db)
) -> OutlookResponse:
    _ensure_model()
    days = []
    version = ""
    in_training_set = False
    generated_at = datetime.now(timezone.utc)
    for row in await _api_feature_rows(data):
        try:
            probability, predicted_flood, _threshold, version = prediction.predict(_feature_payload(row))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        score, level = academic_risk_score(
            float(row["rainfall_mm"]), float(row["river_discharge_m3s"]), probability
        )
        day = row["date"]
        day_in_training = bool(row.get("in_training_set"))
        in_training_set = in_training_set or day_in_training
        days.append(
            {
                "date": day,
                "precipitation_mm": row["rainfall_mm"],
                "discharge_m3_s": row["river_discharge_m3s"],
                "temperature_c": row.get("temperature_c"),
                "relative_humidity_pct": row.get("relative_humidity_pct"),
                "wind_speed_m_s": row.get("wind_speed_m_s"),
                "rainfall_7d_mm": row.get("rainfall_7d_mm"),
                "rainfall_30d_mm": row.get("rainfall_30d_mm"),
                "flood_probability": probability,
                "predicted_flood": bool(predicted_flood),
                "risk_score": score,
                "risk_level": level,
                "alert_recorded": False,
                "forecast_horizon_hours": max(0, (day - data.date).days * 24),
                "input_freshness": {
                    "retrieved_at": generated_at.isoformat(),
                    "rainfall": row.get("rainfall_source") or "Open-Meteo forecast/reanalysis",
                    "meteorology": row.get("meteorology_source") or "NASA POWER",
                    "discharge": row.get("discharge_source")
                    or "Open-Meteo Flood API modeled GloFAS-derived discharge",
                },
                "uncertainty": _outlook_uncertainty(day_in_training),
            }
        )
    return OutlookResponse(
        township_id=data.township_id,
        model_version=version,
        in_training_set=in_training_set,
        days=days,
    )


@router.post("/help/summary", response_model=HelpDay, tags=["humanitarian"])
async def get_help_summary(data: PredictRequest) -> HelpDay:
    """Fast single-day help estimate (archive / rules path without full forecast window)."""
    scored = help_prediction.predict_help_from_flood_and_inventory(
        {},
        planning_date=data.date,
        township_name_en=data.township_name_en,
        township_id=data.township_id,
    )
    male = scored.get("affected_group_a")
    female = scored.get("affected_group_b")
    source = str(scored.get("model_version", ""))
    if source.startswith("flood-help-topredict"):
        impact_source = "ToPredit_Excel_Data.xlsx"
    elif source.endswith("archive-fallback"):
        impact_source = "Local flood archive"
    else:
        impact_source = "Flood-help model estimate"
    return HelpDay(
        date=data.date,
        help_probability=float(scored["help_probability"]),
        predicted_help=bool(scored["predicted_help"]),
        expected_affected_people=int(scored["expected_affected_people"]),
        expected_households=int(scored["expected_households"]),
        affected_male=int(male) if male is not None else None,
        affected_female=int(female) if female is not None else None,
        impact_source=impact_source,
        assistance_priority=str(scored["assistance_priority"]),  # type: ignore[arg-type]
        shelter_kits=int(scored["shelter_kits"]),
        food_rations_3d=int(scored["food_rations_3d"]),
        drinking_water_liters_3d=int(scored["drinking_water_liters_3d"]),
    )


@router.post("/help", response_model=HelpResponse, tags=["humanitarian"])
async def create_help_outlook(data: PredictRequest) -> HelpResponse:
    days = []
    version = "flood-help-v1"
    for row in await _api_feature_rows(data):
        try:
            scored = help_prediction.predict_help(
                _feature_payload(row),
                planning_date=row["date"],
                township_name_en=data.township_name_en,
                township_id=data.township_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        version = str(scored["model_version"])
        days.append(
            {
                "date": row["date"],
                **{key: value for key, value in scored.items() if key != "model_version"},
            }
        )
    return HelpResponse(township_id=data.township_id, model_version=version, days=days)


@router.get("/help-brief", response_model=HelpBriefResponse, tags=["humanitarian"])
def get_help_brief(limit: int = Query(default=5, ge=1, le=20)) -> HelpBriefResponse:
    try:
        brief = flood_history.assistance_brief(limit)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail="Validated flood history is unavailable") from exc
    return HelpBriefResponse.model_validate(brief)


@router.get("/flood-cases/high-severe", response_model=FloodCaseCatalogResponse, tags=["humanitarian"])
def get_flood_cases_high_severe(
    level: Literal["all", "high", "severe"] = Query(default="all"),
    source: Literal["all", "recorded", "model"] = Query(default="all"),
    view: Literal["events", "days"] = Query(default="events"),
    township_id: str | None = Query(default=None),
    year: int | None = Query(default=None, ge=2000, le=2100),
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> FloodCaseCatalogResponse:
    return flood_cases.load_catalog(
        level=level,
        source=source,
        view=view,
        township_id=township_id,
        year=year,
        limit=limit,
        offset=offset,
    )


@router.get("/risk", response_model=RiskResponse, tags=["risk"])
def get_risk(
    precipitation_mm: float = Query(ge=0),
    discharge_m3_s: float = Query(ge=0),
    predicted_value: float = Query(default=0, ge=0),
) -> RiskResponse:
    score, level = academic_risk_score(precipitation_mm, discharge_m3_s, predicted_value)
    return RiskResponse(score=score, level=level)


@router.get("/forecast", response_model=ForecastResponse, tags=["forecast"])
async def get_forecast(
    latitude: float = Query(ge=-90, le=90),
    longitude: float = Query(ge=-180, le=180),
) -> ForecastResponse:
    try:
        weather, discharge = await asyncio.gather(
            clients.open_meteo_forecast(latitude, longitude),
            clients.glofas_discharge_forecast(latitude, longitude),
        )
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=f"Forecast provider error: {exc}") from exc
    return ForecastResponse(
        latitude=latitude,
        longitude=longitude,
        points=_merge_forecast_points(weather, discharge),
    )


@router.get("/bago-areas", response_model=BagoAreasResponse, tags=["historical"])
async def get_bago_areas(session: Session = Depends(get_db)) -> BagoAreasResponse:
    """Bago districts and townships from imported geography, or Open Admin Data fallback."""
    try:
        payload = admin_areas.bago_areas(session)
    except GeographyUnavailableError:
        try:
            payload = open_admin_areas.bundled_bago_areas()
        except ValueError:
            try:
                payload = await open_admin_areas.bago_areas()
            except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
                raise HTTPException(status_code=502, detail=f"Admin area provider error: {exc}") from exc
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=f"Admin area error: {exc}") from exc
    return BagoAreasResponse.model_validate(payload)


@router.get("/townships", response_model=list[TownshipResponse], tags=["historical"])
def get_townships() -> list[TownshipResponse]:
    try:
        rows = flood_history.list_townships()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail="Township catalog is unavailable") from exc
    return [
        TownshipResponse(township_id=item[0], township=item[1], latitude=item[2], longitude=item[3])
        for item in rows
    ]


@router.get("/alerts", response_model=list[AlertResponse], tags=["alerts"])
def get_alerts(
    location_id: int | None = Query(default=None, gt=0),
    level: Literal["low", "moderate", "high", "severe"] | None = None,
    session: Session = Depends(get_db),
) -> list[AlertResponse]:
    return [AlertResponse.model_validate(item) for item in persistence.list_alerts(session, location_id, level)]


@router.get("/historical", response_model=HistoricalResponse, tags=["historical"])
async def get_historical(
    latitude: float = Query(ge=-90, le=90),
    longitude: float = Query(ge=-180, le=180),
    start: date = Query(),
    end: date = Query(),
    township_id: str | None = Query(default=None, min_length=1, max_length=80),
    session: Session = Depends(get_db),
) -> HistoricalResponse:
    if start > end:
        raise HTTPException(status_code=422, detail="start must be on or before end")
    location_key = township_id or f"{latitude:.4f},{longitude:.4f}"
    try:
        nasa = await clients.nasa_power_history(latitude, longitude, start, end)
    except (httpx.HTTPError, ValueError) as exc:
        stored = persistence.list_historical_days(session, location_key, start, end)
        if stored:
            return HistoricalResponse(latitude=latitude, longitude=longitude, points=stored)
        raise HTTPException(status_code=502, detail=f"Historical provider error: {exc}") from exc
    try:
        weather = await clients.open_meteo_daily_weather(
            latitude,
            longitude,
            past_days=max(62, (end - start).days + 1),
            forecast_days=7,
        )
    except (httpx.HTTPError, ValueError):
        weather = []
    weather_by_day = {item["date"]: item for item in weather}

    def _filled(primary: float | None, fallback: float | None) -> float | None:
        return primary if primary is not None else fallback

    points = []
    for point in nasa:
        fill = weather_by_day.get(point.date, {})
        points.append(
            point.model_copy(
                update={
                    "precipitation_mm": _filled(point.precipitation_mm, fill.get("rainfall_mm")),
                    "temperature_c": _filled(point.temperature_c, fill.get("temperature_c")),
                    "relative_humidity_pct": _filled(
                        point.relative_humidity_pct, fill.get("relative_humidity_pct")
                    ),
                    "wind_speed_m_s": _filled(point.wind_speed_m_s, fill.get("wind_speed_m_s")),
                }
            )
        )
    persistence.upsert_historical_days(session, location_key, latitude, longitude, points)
    return HistoricalResponse(latitude=latitude, longitude=longitude, points=points)


@router.get("/flood-history", response_model=FloodHistoryResponse, tags=["historical"])
def get_flood_history(
    township_id: str | None = Query(default=None, min_length=1, max_length=80),
    start: date | None = None,
    end: date | None = None,
    limit: int = Query(default=20, ge=1, le=200),
) -> FloodHistoryResponse:
    if start and end and start > end:
        raise HTTPException(status_code=422, detail="start must be on or before end")
    try:
        matched, records = flood_history.recorded_floods(township_id, start, end, limit)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail="Validated flood history is unavailable") from exc
    return FloodHistoryResponse(matched_records=matched, records=records)


@router.get("/census", tags=["humanitarian"])
def get_census():
    try:
        return load_census()
    except CensusUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/topography", response_model=TopographyResponse, tags=["forecast"])
async def get_topography(
    latitude: float = Query(ge=-90, le=90),
    longitude: float = Query(ge=-180, le=180),
) -> TopographyResponse:
    try:
        point = await clients.opentopography_elevation(latitude, longitude)
    except clients.OpenTopographyConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return TopographyResponse(
        latitude=latitude,
        longitude=longitude,
        elevation_m=float(point["elevation_m"]),
        dataset=str(point["dataset"]),
        vertical_datum_epsg=str(point["vertical_datum_epsg"]),
    )


@router.post("/routes", response_model=RoutePlanResponse, tags=["routing"])
async def create_route(data: RoutePlanRequest) -> RoutePlanResponse:
    if any(stop.id == data.origin.id for stop in data.stops):
        raise HTTPException(status_code=422, detail="Origin cannot also be a delivery stop")
    try:
        return await kardinal.plan_route(data)
    except kardinal.KardinalConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except kardinal.KardinalRequestError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
