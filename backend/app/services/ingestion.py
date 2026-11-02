from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import InundationProduct, OfficialWarning, ProviderObservation
from app.services import clients
from app.services.sources import ensure_sources


@dataclass(frozen=True)
class ObservationRecord:
    source_key: str
    location_key: str
    variable: str
    valid_at: datetime
    retrieved_at: datetime
    unit: str
    value: float | None
    latitude: float
    longitude: float
    quality: str
    observed_at: datetime | None = None
    missing: bool = False
    coverage: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


async def fetch_open_fallback(
    location_key: str,
    latitude: float,
    longitude: float,
    past_days: int = 7,
    forecast_days: int = 7,
) -> list[ObservationRecord]:
    """Fetch public non-commercial fallback data with explicit modeled/forecast quality."""
    import asyncio

    rainfall, discharge = await asyncio.gather(
        clients.open_meteo_daily_precipitation(latitude, longitude, past_days, forecast_days),
        clients.glofas_daily_discharge(latitude, longitude, past_days, forecast_days),
    )
    retrieved_at = datetime.now(timezone.utc)
    today = retrieved_at.date()
    rows: list[ObservationRecord] = []
    for source_key, variable, unit, points in (
        ("open_meteo", "precipitation_sum", "mm", rainfall),
        ("open_meteo_flood", "river_discharge", "m3/s", discharge),
    ):
        for day, value in points:
            valid_at = datetime.combine(day, time.min, tzinfo=timezone.utc)
            rows.append(
                ObservationRecord(
                    source_key=source_key,
                    location_key=location_key,
                    variable=variable,
                    valid_at=valid_at,
                    retrieved_at=retrieved_at,
                    unit=unit,
                    value=value,
                    latitude=latitude,
                    longitude=longitude,
                    quality="forecast" if day >= today else "modeled_or_reanalysis",
                    missing=value is None,
                    coverage={"type": "point", "latitude": latitude, "longitude": longitude},
                    metadata={
                        "forecast_horizon_hours": max(0, (day - today).days * 24),
                        "disclaimer": (
                            "Modeled discharge, not measured water level."
                            if source_key == "open_meteo_flood"
                            else "Gridded weather data, not a local rain gauge."
                        ),
                    },
                )
            )
    return rows


def persist_observations(session: Session, records: list[ObservationRecord]) -> int:
    sources = ensure_sources(session)
    written = 0
    for record in records:
        source = sources[record.source_key]
        existing = session.scalar(
            select(ProviderObservation).where(
                ProviderObservation.source_id == source.id,
                ProviderObservation.variable == record.variable,
                ProviderObservation.location_key == record.location_key,
                ProviderObservation.valid_at == record.valid_at,
            )
        )
        values = {
            "latitude": record.latitude,
            "longitude": record.longitude,
            "value": record.value,
            "unit": record.unit,
            "observed_at": record.observed_at,
            "retrieved_at": record.retrieved_at,
            "quality": record.quality,
            "missing": record.missing,
            "coverage_json": record.coverage,
            "metadata_json": record.metadata,
        }
        if existing is None:
            session.add(
                ProviderObservation(
                    source_id=source.id,
                    location_key=record.location_key,
                    variable=record.variable,
                    valid_at=record.valid_at,
                    **values,
                )
            )
            written += 1
        else:
            for key, value in values.items():
                setattr(existing, key, value)
    session.commit()
    return written


def import_official_warning(session: Session, payload: dict[str, Any]) -> OfficialWarning:
    source = ensure_sources(session)["dmh_myanmar"]
    required = {"external_id", "issued_at", "severity", "message", "source_url"}
    missing = sorted(required - payload.keys())
    if missing:
        raise ValueError(f"Missing warning fields: {', '.join(missing)}")
    if not str(payload["source_url"]).startswith("https://"):
        raise ValueError("Official warning imports require an HTTPS source URL")
    issued_at = datetime.fromisoformat(str(payload["issued_at"]).replace("Z", "+00:00"))
    row = session.scalar(
        select(OfficialWarning).where(
            OfficialWarning.source_id == source.id,
            OfficialWarning.external_id == str(payload["external_id"]),
        )
    )
    values = {
        "issued_at": issued_at,
        "effective_at": _optional_datetime(payload.get("effective_at")),
        "expires_at": _optional_datetime(payload.get("expires_at")),
        "retrieved_at": datetime.now(timezone.utc),
        "severity": str(payload["severity"]),
        "status": str(payload.get("status", "actual")),
        "message": str(payload["message"]),
        "source_url": str(payload["source_url"]),
        "coverage_json": dict(payload.get("coverage") or {}),
    }
    if row is None:
        row = OfficialWarning(
            source_id=source.id,
            external_id=str(payload["external_id"]),
            **values,
        )
        session.add(row)
    else:
        for key, value in values.items():
            setattr(row, key, value)
    session.commit()
    session.refresh(row)
    return row


def import_unosat_geojson(
    session: Session,
    path: Path,
    observed_at: datetime,
    source_url: str,
) -> int:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("type") != "FeatureCollection":
        raise ValueError("UNOSAT import must be a GeoJSON FeatureCollection")
    source = ensure_sources(session)["unosat"]
    imported = 0
    retrieved_at = datetime.now(timezone.utc)
    for index, feature in enumerate(payload.get("features", [])):
        geometry = feature.get("geometry")
        if not geometry:
            continue
        encoded = json.dumps(geometry, sort_keys=True).encode()
        external_id = str(
            (feature.get("properties") or {}).get("id")
            or hashlib.sha256(encoded).hexdigest()[:24]
        )
        exists = session.scalar(
            select(InundationProduct).where(
                InundationProduct.source_id == source.id,
                InundationProduct.external_id == external_id,
            )
        )
        if exists:
            continue
        session.add(
            InundationProduct(
                source_id=source.id,
                external_id=external_id,
                observed_at=observed_at,
                retrieved_at=retrieved_at,
                geometry_json=geometry,
                quality="satellite_detected_unvalidated_in_field",
                metadata_json={
                    "source_url": source_url,
                    "feature_index": index,
                    "limitations": (
                        "Radar flood mapping may miss water in built-up or densely vegetated areas."
                    ),
                },
            )
        )
        imported += 1
    session.commit()
    return imported


def _optional_datetime(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
