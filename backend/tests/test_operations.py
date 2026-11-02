import asyncio
from datetime import datetime, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db import Base
from app.models import OfficialWarning, ProviderObservation
from app.services import ingestion, scheduler, sources


def test_source_registry_labels_disabled_authoritative_feeds() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        statuses = {row["key"]: row for row in sources.source_status(session)}
        assert statuses["dmh_myanmar"]["enabled"] is False
        assert "machine-readable" in statuses["dmh_myanmar"]["unavailable_reason"]
        assert statuses["open_meteo_flood"]["enabled"] is True
        assert "Modeled" in statuses["open_meteo_flood"]["attribution"]


def test_observation_ingestion_is_idempotent_and_preserves_missingness() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    valid_at = datetime(2026, 10, 15, tzinfo=timezone.utc)
    row = ingestion.ObservationRecord(
        source_key="open_meteo",
        location_key="MMR007001",
        variable="precipitation_sum",
        valid_at=valid_at,
        retrieved_at=valid_at,
        unit="mm",
        value=None,
        latitude=18,
        longitude=96,
        quality="forecast",
        missing=True,
    )
    with Session(engine) as session:
        assert ingestion.persist_observations(session, [row]) == 1
        assert ingestion.persist_observations(session, [row]) == 0
        saved = session.scalars(select(ProviderObservation)).all()
        assert len(saved) == 1
        assert saved[0].missing is True
        assert saved[0].unit == "mm"


def test_official_warning_requires_traceable_source_and_deduplicates() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    payload = {
        "external_id": "dmh-2026-001",
        "issued_at": "2026-10-15T06:30:00+06:30",
        "severity": "warning",
        "message": "Imported operator-verified DMH bulletin.",
        "source_url": "https://www.moezala.gov.mm/example",
        "coverage": {"station": "Bago"},
    }
    with Session(engine) as session:
        first = ingestion.import_official_warning(session, payload)
        second = ingestion.import_official_warning(session, payload)
        assert first.id == second.id
        assert len(session.scalars(select(OfficialWarning)).all()) == 1


def test_myanmar_schedule_accepts_only_two_or_three_unique_times() -> None:
    assert len(scheduler.configured_times("06:00,18:00")) == 2
    assert len(scheduler.configured_times("06:00,12:00,18:00")) == 3
    for invalid in ("06:00", "06:00,06:00", "01:00,02:00,03:00,04:00"):
        try:
            scheduler.configured_times(invalid)
        except ValueError:
            pass
        else:
            raise AssertionError(f"{invalid} must be rejected")


def test_job_claim_suppresses_duplicate_slot() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    slot = datetime(2026, 10, 15, 0, tzinfo=timezone.utc)
    with Session(engine) as session:
        first = scheduler.claim_run(session, "prediction", slot)
        second = scheduler.claim_run(session, "prediction", slot)
        assert first is not None
        assert second is None
