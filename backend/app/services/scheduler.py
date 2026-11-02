from __future__ import annotations

import asyncio
import os
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import AdminArea, JobRun, RiskResult
from app.services import geography, ingestion
from app.services.risk import academic_risk_score

MYANMAR_TZ = ZoneInfo("Asia/Yangon")
DEFAULT_TIMES = "06:00,12:00,18:00"
MAX_ATTEMPTS = 3


def configured_times(value: str | None = None) -> tuple[time, ...]:
    raw = value if value is not None else os.getenv("PREDICTION_TIMES_MMT", DEFAULT_TIMES)
    values = tuple(time.fromisoformat(item.strip()) for item in raw.split(",") if item.strip())
    if len(values) not in (2, 3):
        raise ValueError("PREDICTION_TIMES_MMT must contain exactly two or three HH:MM times")
    if len(set(values)) != len(values):
        raise ValueError("PREDICTION_TIMES_MMT times must be unique")
    return tuple(sorted(values))


def scheduled_slots(now: datetime | None = None) -> tuple[datetime, ...]:
    current = (now or datetime.now(timezone.utc)).astimezone(MYANMAR_TZ)
    return tuple(
        datetime.combine(current.date(), configured, tzinfo=MYANMAR_TZ).astimezone(timezone.utc)
        for configured in configured_times()
    )


def due_slots(now: datetime | None = None) -> tuple[datetime, ...]:
    current = now or datetime.now(timezone.utc)
    # A twelve-hour window recovers missed slots after a restart without replaying old days.
    return tuple(
        slot for slot in scheduled_slots(current) if timedelta(0) <= current - slot <= timedelta(hours=12)
    )


def _run_key(job_name: str, scheduled_for: datetime) -> str:
    return f"{job_name}:{scheduled_for.astimezone(timezone.utc).isoformat(timespec='minutes')}"


def claim_run(session: Session, job_name: str, scheduled_for: datetime, manual: bool = False) -> JobRun | None:
    key = _run_key(job_name, scheduled_for)
    row = session.scalar(select(JobRun).where(JobRun.idempotency_key == key))
    if row is not None:
        if row.status != "failed" or row.attempt >= MAX_ATTEMPTS:
            return None
        row.status = "running"
        row.attempt += 1
        row.started_at = datetime.now(timezone.utc)
        row.finished_at = None
        row.error = None
        session.commit()
        return row
    row = JobRun(
        idempotency_key=key,
        job_name=job_name,
        scheduled_for=scheduled_for,
        started_at=datetime.now(timezone.utc),
        status="running",
        attempt=1,
        config_json={
            "timezone": "Asia/Yangon",
            "manual": manual,
            "prediction_times": [item.strftime("%H:%M") for item in configured_times()],
        },
    )
    session.add(row)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        return None
    session.refresh(row)
    return row


async def execute_prediction_run(
    session: Session,
    scheduled_for: datetime,
    manual: bool = False,
) -> JobRun | None:
    run = claim_run(session, "prediction", scheduled_for, manual)
    if run is None:
        return None
    errors: list[str] = []
    completed = 0
    freshest: datetime | None = None
    try:
        version_id = geography.latest_dataset_id(session)
        townships = session.scalars(
            select(AdminArea).where(
                AdminArea.dataset_version_id == version_id,
                AdminArea.level == 3,
            )
        ).all()
        for area in townships:
            if area.centroid_latitude is None or area.centroid_longitude is None:
                errors.append(f"{area.source_code}: missing verified centroid")
                continue
            try:
                records = await ingestion.fetch_open_fallback(
                    area.source_code,
                    area.centroid_latitude,
                    area.centroid_longitude,
                )
                ingestion.persist_observations(session, records)
                completed += 1
                for record in records:
                    freshest = max(freshest or record.retrieved_at, record.retrieved_at)
                await _save_heuristic_results(session, run, area, records)
            except Exception as exc:  # individual provider/location failures must not erase coverage
                errors.append(f"{area.source_code}: {type(exc).__name__}: {exc}")
        run.coverage_json = {
            "requested_townships": len(townships),
            "completed_townships": completed,
            "incomplete_townships": len(townships) - completed,
        }
        run.freshness_json = {
            "retrieved_at": freshest.isoformat() if freshest else None,
            "complete": not errors,
        }
        run.status = "succeeded" if not errors else ("partial" if completed else "failed")
        run.error = "\n".join(errors) if errors else None
    except Exception as exc:
        run.status = "failed"
        run.error = f"{type(exc).__name__}: {exc}"
    run.finished_at = datetime.now(timezone.utc)
    session.commit()
    return run


async def _save_heuristic_results(
    session: Session,
    run: JobRun,
    area: AdminArea,
    records: list[ingestion.ObservationRecord],
) -> None:
    rain = {item.valid_at: item for item in records if item.variable == "precipitation_sum"}
    discharge = {item.valid_at: item for item in records if item.variable == "river_discharge"}
    now = datetime.now(timezone.utc)
    for valid_at in sorted(set(rain) & set(discharge)):
        rain_row, discharge_row = rain[valid_at], discharge[valid_at]
        if rain_row.value is None or discharge_row.value is None:
            continue
        score, level = academic_risk_score(rain_row.value, discharge_row.value)
        existing = session.scalar(
            select(RiskResult).where(
                RiskResult.job_run_id == run.id,
                RiskResult.admin_area_id == area.id,
                RiskResult.valid_at == valid_at,
                RiskResult.evidence_type == "heuristic_risk",
            )
        )
        if existing:
            continue
        session.add(
            RiskResult(
                job_run_id=run.id,
                admin_area_id=area.id,
                valid_at=valid_at,
                forecast_horizon_hours=max(0, round((valid_at - now).total_seconds() / 3600)),
                evidence_type="heuristic_risk",
                risk_level=level,
                risk_score=score,
                probability=None,
                input_freshness_json={
                    "rainfall_retrieved_at": rain_row.retrieved_at.isoformat(),
                    "discharge_retrieved_at": discharge_row.retrieved_at.isoformat(),
                },
                supporting_evidence_json={
                    "precipitation_mm": rain_row.value,
                    "modeled_discharge_m3_s": discharge_row.value,
                    "method": "transparent academic_risk_score thresholds",
                },
                uncertainty_json={
                    "status": "provisional",
                    "note": "Not a probability or official warning; no local gauge validation.",
                },
            )
        )
    session.commit()


async def run_worker() -> None:
    configured_times()  # fail fast on invalid configuration
    while True:
        for slot in due_slots():
            with SessionLocal() as session:
                await execute_prediction_run(session, slot)
        await asyncio.sleep(30)


def serialize_run(row: JobRun) -> dict[str, object]:
    return {
        "id": row.id,
        "job_name": row.job_name,
        "scheduled_for": row.scheduled_for,
        "started_at": row.started_at,
        "finished_at": row.finished_at,
        "status": row.status,
        "attempt": row.attempt,
        "model_version": row.model_version,
        "freshness": row.freshness_json,
        "coverage": row.coverage_json,
        "error": row.error,
    }
