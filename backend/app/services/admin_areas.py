"""Compatibility facade for the database-backed, versioned geography service."""

from sqlalchemy.orm import Session

from app.services.geography import (
    GeographyUnavailableError,
    bago_area_response,
    hierarchy,
    import_mimu_v97,
    import_ocha_geojson,
    relief_slug_for_area,
    validate_bago_geography,
)


def bago_areas(session: Session):
    return bago_area_response(session)


__all__ = [
    "GeographyUnavailableError",
    "bago_areas",
    "hierarchy",
    "import_mimu_v97",
    "import_ocha_geojson",
    "relief_slug_for_area",
    "validate_bago_geography",
]
