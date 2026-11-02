from datetime import date

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.api import (
    PredictionMapScoresResponse,
    PredictionTimelineRequest,
    PredictionTimelineResponse,
)
from app.services import admin_areas, prediction as prediction_service
from app.services.daily_catalog import calendar_bounds
from app.services.forecast_store import RegionForecastResponse, build_region_forecast
from app.services.prediction_timeline import build_timeline, local_today, map_scores_for_date

router = APIRouter(tags=["prediction"])


def _ensure_model() -> None:
    try:
        prediction_service.load_model()
    except prediction_service.ModelUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/prediction/calendar-bounds")
def get_prediction_calendar_bounds() -> dict[str, str | None]:
    """Selectable timeline dates: hindcast from 2010 through live forecast (+7 days)."""
    return calendar_bounds(local_today())


@router.get("/prediction/township/{township_id}/hazard-surface")
def get_township_hazard_surface(township_id: str) -> dict[str, object]:
    """JRC/HAND static hazard summary for map panel (local raster clips when ingested)."""
    from app.services.hydro_offline_db import static_features

    features = static_features(township_id)
    if not features:
        return {
            "township_id": township_id,
            "status": "unavailable",
            "detail": "Run ml/flood/ingest_rasters.py after placing Bago clips under data/external/rasters/.",
        }
    preview = features.get("hazard_preview_path")
    return {
        "township_id": township_id,
        "status": "ready",
        "jrc_depth_100y_max_m": features.get("jrc_depth_100y_max_m"),
        "jrc_pct_inundated_100y": features.get("jrc_pct_inundated_100y"),
        "hand_min_m": features.get("hand_min_m"),
        "hand_pct_lt_2m": features.get("hand_pct_lt_2m"),
        "worldcover_pct_built_floodplain": features.get("worldcover_pct_built_floodplain"),
        "worldcover_pct_crop_floodplain": features.get("worldcover_pct_crop_floodplain"),
        "hazard_preview_path": preview,
        "hydrobasin_id": features.get("hydrobasin_id"),
    }


@router.post("/prediction/timeline", response_model=PredictionTimelineResponse)
async def create_prediction_timeline(
    data: PredictionTimelineRequest,
    session: Session = Depends(get_db),
) -> PredictionTimelineResponse:
    _ensure_model()
    as_of = data.as_of or local_today()
    relief_slug = admin_areas.relief_slug_for_area(session, data.township_id)
    try:
        payload = await build_timeline(
            data.township_id,
            data.latitude,
            data.longitude,
            as_of,
            township_name_en=data.township_name_en,
            relief_slug=relief_slug or data.township_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Forecast provider error: {exc}") from exc

    return PredictionTimelineResponse.model_validate(payload)


@router.get("/prediction/map-scores", response_model=PredictionMapScoresResponse)
async def get_prediction_map_scores(
    date: str = Query(..., description="Calendar date YYYY-MM-DD"),
    district_id: str | None = Query(default=None, min_length=1, max_length=80),
    session: Session = Depends(get_db),
) -> PredictionMapScoresResponse:
    _ensure_model()
    try:
        from datetime import date as date_type

        target = date_type.fromisoformat(date)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="date must be YYYY-MM-DD") from exc
    try:
        payload = await map_scores_for_date(session, target, district_id)
    except prediction_service.ModelUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return PredictionMapScoresResponse.model_validate(payload)


@router.get("/prediction/region-forecast", response_model=RegionForecastResponse)
async def get_region_forecast(
    as_of: date | None = None,
    lead_days: int | None = Query(default=None, ge=0, le=3),
    district_id: str | None = Query(default=None),
    session: Session = Depends(get_db),
) -> RegionForecastResponse:
    """Persisted scores for every Bago township on as_of and lead days +1, +2, and +3."""
    _ensure_model()
    target = as_of or local_today()
    try:
        payload = await build_region_forecast(session, target)
    except prediction_service.ModelUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if lead_days is None and not district_id:
        return payload
    scores = [
        score
        for score in payload.scores
        if (lead_days is None or score.lead_days == lead_days)
        and (not district_id or score.district_id == district_id)
    ]
    return payload.model_copy(update={"scores": scores})
