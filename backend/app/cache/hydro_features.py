"""Local hydrology cache. Writes commit on this file only."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import JSON, Date, DateTime, String, UniqueConstraint, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from app.cache.sqlite import resolve_cache_path, sqlite_engine

CACHE_ENV = "HYDRO_FEATURES_CACHE"
CACHE_RELATIVE = "data/cache/hydro_features.sqlite"


class HydroCacheBase(DeclarativeBase):
    pass


class DailyObservation(HydroCacheBase):
    __tablename__ = "daily_observations"
    __table_args__ = (
        UniqueConstraint("township_id", "date", "source", name="uq_hydro_daily_observation"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    township_id: Mapped[str] = mapped_column(String(80), index=True)
    observed_on: Mapped[date] = mapped_column(Date, name="date", nullable=False)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class EngineeredFeature(HydroCacheBase):
    __tablename__ = "engineered_features"
    __table_args__ = (
        UniqueConstraint(
            "township_id",
            "date",
            "feature_version",
            name="uq_hydro_engineered_feature",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    township_id: Mapped[str] = mapped_column(String(80), index=True)
    observed_on: Mapped[date] = mapped_column(Date, name="date", nullable=False)
    feature_version: Mapped[str] = mapped_column(String(80), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)


def cache_path() -> Path:
    return resolve_cache_path(CACHE_ENV, CACHE_RELATIVE)


def feature_engine():
    return sqlite_engine(cache_path(), HydroCacheBase.metadata)


def upsert_daily_observation(
    *,
    township_id: str,
    observed_on: date,
    source: str,
    payload: dict,
    fetched_at: datetime | None = None,
) -> None:
    """Store one raw provider payload. This session is not the operational session."""
    stamp = fetched_at or datetime.now(timezone.utc)
    with Session(feature_engine()) as session:
        row = session.scalar(
            select(DailyObservation).where(
                DailyObservation.township_id == township_id,
                DailyObservation.observed_on == observed_on,
                DailyObservation.source == source,
            )
        )
        if row is None:
            session.add(
                DailyObservation(
                    township_id=township_id,
                    observed_on=observed_on,
                    source=source,
                    payload=payload,
                    fetched_at=stamp,
                )
            )
        else:
            row.payload = payload
            row.fetched_at = stamp
        session.commit()


def upsert_engineered_feature(
    *,
    township_id: str,
    observed_on: date,
    feature_version: str,
    payload: dict,
) -> None:
    with Session(feature_engine()) as session:
        row = session.scalar(
            select(EngineeredFeature).where(
                EngineeredFeature.township_id == township_id,
                EngineeredFeature.observed_on == observed_on,
                EngineeredFeature.feature_version == feature_version,
            )
        )
        if row is None:
            session.add(
                EngineeredFeature(
                    township_id=township_id,
                    observed_on=observed_on,
                    feature_version=feature_version,
                    payload=payload,
                )
            )
        else:
            row.payload = payload
        session.commit()


def list_daily_observations() -> list[dict[str, object]]:
    with Session(feature_engine()) as session:
        rows = session.scalars(select(DailyObservation).order_by(DailyObservation.id)).all()
        return [
            {
                "township_id": row.township_id,
                "date": row.observed_on,
                "source": row.source,
                "payload": row.payload,
                "fetched_at": row.fetched_at,
            }
            for row in rows
        ]
