"""Town-seat coordinates for maps and road routing (not hydrology grids)."""

from __future__ import annotations

from app.services.open_admin_areas import _name_key, _township_map_labels


def resolve_township_map_coords(
    name_en: str,
    fallback_lat: float,
    fallback_lon: float,
) -> tuple[float, float]:
    labels = _township_map_labels()
    return labels.get(_name_key(name_en), (fallback_lat, fallback_lon))
