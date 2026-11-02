from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import (
    AdminArea,
    DataSource,
    ExposureSummary,
    InundationProduct,
    JobRun,
    OfficialWarning,
    RiskResult,
    Settlement,
)
from app.schemas.api import (
    AdminHierarchyResponse,
    ExposureSummaryResponse,
    JobRunResponse,
    OfficialWarningResponse,
    SettlementResponse,
    SourceStatusResponse,
)
from app.security import require_admin_key
from app.services import geography, ingestion, scheduler, sources

router = APIRouter()


@router.get("/sources", response_model=list[SourceStatusResponse], tags=["provenance"])
def get_sources(session: Session = Depends(get_db)):
    return sources.source_status(session)


@router.get("/admin-areas", response_model=AdminHierarchyResponse, tags=["geography"])
def get_admin_areas(
    max_level: int = Query(default=5, ge=1, le=5),
    search: str | None = Query(default=None, max_length=120),
    session: Session = Depends(get_db),
):
    return geography.hierarchy(session, max_level=max_level, query=search)


@router.get("/official-warnings", response_model=list[OfficialWarningResponse], tags=["warnings"])
def get_official_warnings(
    limit: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_db),
):
    rows = session.execute(
        select(OfficialWarning, DataSource)
        .join(DataSource, OfficialWarning.source_id == DataSource.id)
        .order_by(desc(OfficialWarning.issued_at))
        .limit(limit)
    ).all()
    return [
        {
            "id": warning.id,
            "source": source.name,
            "external_id": warning.external_id,
            "issued_at": warning.issued_at,
            "effective_at": warning.effective_at,
            "expires_at": warning.expires_at,
            "severity": warning.severity,
            "status": warning.status,
            "message": warning.message,
            "source_url": warning.source_url,
            "coverage": warning.coverage_json,
        }
        for warning, source in rows
    ]


@router.post(
    "/official-warnings/import",
    response_model=OfficialWarningResponse,
    tags=["warnings"],
    dependencies=[Depends(require_admin_key)],
)
def create_official_warning(payload: dict, session: Session = Depends(get_db)):
    try:
        row = ingestion.import_official_warning(session, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "id": row.id,
        "source": "Myanmar Department of Meteorology and Hydrology",
        "external_id": row.external_id,
        "issued_at": row.issued_at,
        "effective_at": row.effective_at,
        "expires_at": row.expires_at,
        "severity": row.severity,
        "status": row.status,
        "message": row.message,
        "source_url": row.source_url,
        "coverage": row.coverage_json,
    }


@router.get("/inundation-products", tags=["inundation"])
def get_inundation_products(
    limit: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_db),
):
    rows = session.scalars(
        select(InundationProduct).order_by(desc(InundationProduct.observed_at)).limit(limit)
    ).all()
    return [
        {
            "id": row.id,
            "evidence_type": "observed_inundation",
            "observed_at": row.observed_at,
            "retrieved_at": row.retrieved_at,
            "geometry": row.geometry_json,
            "quality": row.quality,
            "affected_population": row.affected_population,
            "population_source": row.population_source,
            "metadata": row.metadata_json,
        }
        for row in rows
    ]


@router.get("/risk-results", tags=["prediction"])
def get_risk_results(
    limit: int = Query(default=200, ge=1, le=1000),
    session: Session = Depends(get_db),
):
    rows = session.scalars(
        select(RiskResult).order_by(desc(RiskResult.valid_at), desc(RiskResult.id)).limit(limit)
    ).all()
    return [
        {
            "id": row.id,
            "admin_area_id": row.admin_area_id,
            "valid_at": row.valid_at,
            "forecast_horizon_hours": row.forecast_horizon_hours,
            "evidence_type": row.evidence_type,
            "risk_level": row.risk_level,
            "risk_score": row.risk_score,
            "probability": row.probability,
            "input_freshness": row.input_freshness_json,
            "supporting_evidence": row.supporting_evidence_json,
            "uncertainty": row.uncertainty_json,
        }
        for row in rows
    ]


@router.get("/runs", response_model=list[JobRunResponse], tags=["operations"])
def get_runs(
    limit: int = Query(default=20, ge=1, le=200),
    session: Session = Depends(get_db),
):
    rows = session.scalars(select(JobRun).order_by(desc(JobRun.started_at)).limit(limit)).all()
    return [scheduler.serialize_run(row) for row in rows]


@router.post(
    "/runs/prediction",
    response_model=JobRunResponse,
    tags=["operations"],
    dependencies=[Depends(require_admin_key)],
)
async def create_prediction_run(session: Session = Depends(get_db)):
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    row = await scheduler.execute_prediction_run(session, now, manual=True)
    if row is None:
        row = session.scalar(
            select(JobRun).where(JobRun.idempotency_key == f"prediction:{now.isoformat(timespec='minutes')}")
        )
    if row is None:
        raise HTTPException(status_code=409, detail="Prediction run was not claimed")
    return scheduler.serialize_run(row)


@router.get("/settlements", response_model=list[SettlementResponse], tags=["geography"])
def get_settlements(
    limit: int = Query(default=5000, ge=1, le=5000),
    admin_area_code: str | None = Query(default=None, max_length=80),
    session: Session = Depends(get_db),
) -> list[SettlementResponse]:
    statement = select(Settlement).order_by(Settlement.id)
    if admin_area_code:
        statement = statement.join(AdminArea, Settlement.admin_area_id == AdminArea.id).where(
            AdminArea.source_code == admin_area_code
        )
    rows = session.scalars(statement.limit(limit)).all()
    return [
        SettlementResponse(
            id=row.id,
            source_code=row.source_code,
            admin_area_id=row.admin_area_id,
            name_en=row.name_en,
            name_local=row.name_local,
            settlement_type=row.settlement_type,
            latitude=row.latitude,
            longitude=row.longitude,
            verification_status=row.verification_status,
        )
        for row in rows
    ]


@router.get("/exposure-summaries", response_model=list[ExposureSummaryResponse], tags=["inundation"])
def get_exposure_summaries(
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_db),
) -> list[ExposureSummaryResponse]:
    rows = session.scalars(select(ExposureSummary).order_by(ExposureSummary.id).limit(limit)).all()
    return [
        ExposureSummaryResponse(
            id=row.id,
            inundation_product_id=row.inundation_product_id,
            admin_area_id=row.admin_area_id,
            population_source=row.population_source,
            exposed_population=row.exposed_population,
            calculated_at=row.calculated_at,
            method=row.method,
            uncertainty=row.uncertainty_json or {},
        )
        for row in rows
    ]
