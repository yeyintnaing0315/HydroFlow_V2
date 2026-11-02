from datetime import date, datetime, time, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Alert, HistoricalDay, Location, Observation
from app.schemas.api import AlertCreate, HistoricalPoint


def get_or_create_location(
    session: Session, name: str, latitude: float, longitude: float
) -> Location:
    existing = session.scalar(select(Location).where(Location.name == name))
    if existing is not None:
        return existing
    location = Location(name=name, latitude=latitude, longitude=longitude)
    session.add(location)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = session.scalar(select(Location).where(Location.name == name))
        if existing is None:
            raise
        return existing
    session.refresh(location)
    return location


def add_alert(session: Session, data: AlertCreate) -> Alert:
    alert = Alert(**data.model_dump())
    session.add(alert)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = session.scalar(
            select(Alert).where(
                Alert.location_id == data.location_id,
                Alert.issued_at == data.issued_at,
                Alert.level == data.level,
            )
        )
        if existing is None:
            raise
        return existing
    session.refresh(alert)
    return alert


def list_alerts(
    session: Session, location_id: int | None = None, level: str | None = None
) -> list[Alert]:
    statement = select(Alert).order_by(Alert.issued_at.desc())
    if location_id is not None:
        statement = statement.where(Alert.location_id == location_id)
    if level is not None:
        statement = statement.where(Alert.level == level)
    return list(session.scalars(statement))


def list_observations(
    session: Session, location_id: int, start: date | None = None, end: date | None = None
) -> list[Observation]:
    statement = (
        select(Observation)
        .where(Observation.location_id == location_id)
        .order_by(Observation.observed_at)
    )
    if start:
        statement = statement.where(
            Observation.observed_at >= datetime.combine(start, time.min, timezone.utc)
        )
    if end:
        statement = statement.where(
            Observation.observed_at <= datetime.combine(end, time.max, timezone.utc)
        )
    return list(session.scalars(statement))


def upsert_historical_days(
    session: Session,
    location_key: str,
    latitude: float,
    longitude: float,
    points: list[HistoricalPoint],
    source: str = "nasa-power",
) -> int:
    """Store API history so later requests can read the same days from the database."""
    retrieved_at = datetime.now(timezone.utc)
    written = 0
    for point in points:
        existing = session.scalar(
            select(HistoricalDay).where(
                HistoricalDay.location_key == location_key,
                HistoricalDay.observed_on == point.date,
            )
        )
        if existing is None:
            session.add(
                HistoricalDay(
                    location_key=location_key,
                    latitude=latitude,
                    longitude=longitude,
                    observed_on=point.date,
                    precipitation_mm=point.precipitation_mm,
                    temperature_c=point.temperature_c,
                    relative_humidity_pct=point.relative_humidity_pct,
                    wind_speed_m_s=point.wind_speed_m_s,
                    source=source,
                    retrieved_at=retrieved_at,
                )
            )
        else:
            existing.latitude = latitude
            existing.longitude = longitude
            existing.precipitation_mm = point.precipitation_mm
            existing.temperature_c = point.temperature_c
            existing.relative_humidity_pct = point.relative_humidity_pct
            existing.wind_speed_m_s = point.wind_speed_m_s
            existing.source = source
            existing.retrieved_at = retrieved_at
        written += 1
    session.commit()
    return written


def list_historical_days(
    session: Session, location_key: str, start: date, end: date
) -> list[HistoricalPoint]:
    rows = session.scalars(
        select(HistoricalDay)
        .where(
            HistoricalDay.location_key == location_key,
            HistoricalDay.observed_on >= start,
            HistoricalDay.observed_on <= end,
        )
        .order_by(HistoricalDay.observed_on)
    )
    return [
        HistoricalPoint(
            date=row.observed_on,
            precipitation_mm=row.precipitation_mm,
            temperature_c=row.temperature_c,
            relative_humidity_pct=row.relative_humidity_pct,
            wind_speed_m_s=row.wind_speed_m_s,
        )
        for row in rows
    ]
