"""Township flood prior from local polygons and river proxies.

JRC flood hazard, Copernicus/FABDEM elevation, MERIT Hydro, WorldCover, and
HydroBASINS are not sampled here. Those rasters are not in the repository, and
this module does not download them. The prior is the distance from the township
centroid to the nearest point in ``bago_river_points.csv``, plus a local basin
label from the 2022 district list. Missing raster names are returned so callers
can store them on the feature payload.
"""

from __future__ import annotations

import csv
import math
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

FEATURE_VERSION = "v2-river-distance-prior"
# River proxies in bago_river_points.csv all sit near 96.4 E. Townships west of
# this line have no stored upstream coordinate.
EAST_LON = 96.15
RASTER_GAPS = (
    "JRC global river flood hazard v2.1",
    "Copernicus DEM GLO-30 or FABDEM",
    "MERIT Hydro",
    "ESA WorldCover",
    "HydroBASINS",
)
_RASTER_SUFFIXES = {".tif", ".tiff", ".nc", ".grd", ".vrt", ".img"}
_RASTER_KEYS = {
    "JRC global river flood hazard v2.1": ("jrc", "floodhazard"),
    "Copernicus DEM GLO-30 or FABDEM": ("fabdem", "copernicus_dem", "glo30", "copdem"),
    "MERIT Hydro": ("merit",),
    "ESA WorldCover": ("worldcover",),
    "HydroBASINS": ("hydrobasin", "hybas"),
}
_EAST_DISTRICTS = {"bago", "nyaunglebin", "taungoo"}


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lam = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lam / 2) ** 2
    return 2 * radius * math.asin(min(1.0, math.sqrt(max(0.0, a))))


def hazard_from_distance_km(distance_km: float | None) -> float | None:
    """Closer to a river proxy means a higher susceptibility prior, on 0–1."""
    if distance_km is None:
        return None
    return round(max(0.0, min(1.0, 1.0 / (1.0 + float(distance_km) / 15.0))), 4)


def load_river_points(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8", newline="") as handle:
        for raw in csv.DictReader(handle):
            try:
                rows.append(
                    {
                        "township": str(raw["township"]),
                        "district": str(raw["district"]),
                        "code": str(raw["code"]),
                        "weather_latitude": float(raw["weather_latitude"]),
                        "weather_longitude": float(raw["weather_longitude"]),
                        "river_latitude": float(raw["river_latitude"]),
                        "river_longitude": float(raw["river_longitude"]),
                    }
                )
            except (KeyError, TypeError, ValueError):
                continue
    return rows


def nearest_river(
    latitude: float, longitude: float, rivers: Sequence[Mapping[str, Any]]
) -> dict[str, Any] | None:
    if not rivers:
        return None
    return min(
        rivers,
        key=lambda row: haversine_km(
            latitude,
            longitude,
            float(row["river_latitude"]),
            float(row["river_longitude"]),
        ),
    )


def centroid_river_distance_km(
    latitude: float, longitude: float, rivers: Sequence[Mapping[str, Any]]
) -> float | None:
    river = nearest_river(latitude, longitude, rivers)
    if river is None:
        return None
    return round(
        haversine_km(
            latitude,
            longitude,
            float(river["river_latitude"]),
            float(river["river_longitude"]),
        ),
        3,
    )


def point_features(
    latitude: float, longitude: float, rivers: Sequence[Mapping[str, Any]]
) -> dict[str, float]:
    """Model columns that training and live scoring both fill from the centroid."""
    distance = centroid_river_distance_km(latitude, longitude, rivers)
    hazard = hazard_from_distance_km(distance)
    features: dict[str, float] = {}
    if distance is not None:
        features["river_distance_km"] = distance
    if hazard is not None:
        features["static_hazard"] = hazard
    return features


def basin_id(district_name: str | None, longitude: float) -> str:
    """Local Sittaung/Bago versus Ayeyarwady split. Not a HydroBASINS id."""
    if district_name and district_name.casefold() in _EAST_DISTRICTS:
        return "sittaung_bago"
    if district_name:
        return "ayeyarwady"
    return "sittaung_bago" if longitude >= EAST_LON else "ayeyarwady"


def upstream_spec(
    latitude: float, longitude: float, rivers: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Upstream rainfall targets, or an explicit centroid-only fallback.

    HydroBASINS centroids are not on disk. When ``bago_river_points.csv`` has
    river proxies north of an eastern township, those proxies are the upstream
    sample (rivers in this region drain south). Western townships have no
    proxy in that file, so rainfall stays at the township centroid.
    """
    fallback = {
        "mode": "centroid_only_fallback",
        "latitude": latitude,
        "longitude": longitude,
        "points": [],
        "note": (
            "No upstream HydroBASINS centroid or river proxy is stored for this "
            "township. Rainfall features use the township centroid only."
        ),
    }
    if not rivers or longitude < EAST_LON:
        return fallback
    north = [
        row
        for row in rivers
        if float(row["weather_latitude"]) >= latitude + 0.15
        and float(row["weather_longitude"]) >= EAST_LON
    ]
    if not north:
        fallback["note"] = (
            "Stored river proxies are not upstream of this township, and "
            "HydroBASINS centroids are not on disk. Rainfall features use the "
            "township centroid only."
        )
        return fallback
    chosen = sorted(north, key=lambda row: float(row["weather_latitude"]), reverse=True)[:3]
    return {
        "mode": "upstream_river_proxy",
        "latitude": latitude,
        "longitude": longitude,
        "points": [
            {
                "township": row["township"],
                "code": row["code"],
                "latitude": float(row["weather_latitude"]),
                "longitude": float(row["weather_longitude"]),
            }
            for row in chosen
        ],
        "note": (
            "Basin rainfall is the mean of Open-Meteo precipitation at the "
            "northern river proxies in bago_river_points.csv. HydroBASINS "
            "polygons are not on disk."
        ),
    }


def _walk_coords(node: Any, found: list[tuple[float, float]]) -> None:
    if isinstance(node, (list, tuple)):
        if (
            len(node) >= 2
            and isinstance(node[0], (int, float))
            and isinstance(node[1], (int, float))
            and not isinstance(node[0], bool)
        ):
            found.append((float(node[0]), float(node[1])))
            return
        for item in node:
            _walk_coords(item, found)


def boundary_river_distance_km(
    geometry: Mapping[str, Any] | None,
    rivers: Sequence[Mapping[str, Any]],
) -> float | None:
    """Minimum distance from a sample of polygon vertices to a river proxy."""
    if not geometry or not rivers:
        return None
    coords: list[tuple[float, float]] = []
    _walk_coords(geometry.get("coordinates"), coords)
    if not coords:
        return None
    step = max(1, len(coords) // 60)
    best: float | None = None
    for longitude, latitude in coords[::step]:
        river = nearest_river(latitude, longitude, rivers)
        if river is None:
            continue
        distance = haversine_km(
            latitude,
            longitude,
            float(river["river_latitude"]),
            float(river["river_longitude"]),
        )
        best = distance if best is None else min(best, distance)
    return None if best is None else round(best, 3)


def missing_raster_inputs(root: Path | None = None) -> list[str]:
    """Names of global layers that are not present as local raster files."""
    data_root = (root or project_root()) / "data"
    haystack: list[str] = []
    if data_root.is_dir():
        for path in data_root.rglob("*"):
            if not path.is_file():
                continue
            name = path.name.casefold()
            if path.suffix.lower() in _RASTER_SUFFIXES or any(
                key in name for keys in _RASTER_KEYS.values() for key in keys
            ):
                haystack.append(str(path).casefold())
    missing: list[str] = []
    for label, keys in _RASTER_KEYS.items():
        if not any(any(key in item for key in keys) for item in haystack):
            missing.append(label)
    return missing


def discover_label_path(root: Path | None = None) -> Path | None:
    """Find an existing relief label file. Do not invent flood days."""
    configured = os.getenv("FLOOD_LABEL_PATH")
    if configured:
        candidate = Path(configured)
        if candidate.is_file():
            return candidate
    project = root or project_root()
    roots = (
        project,
        project.parent / "HydroFlow_V1",
        project.parent / "HydroFlow-V_1.2",
        project.parent / "HydroFlow_1.1",
    )
    relatives = (
        Path("data/processed/validated_daily.csv"),
        Path("data/raw/bago_daily.csv"),
    )
    for relative in relatives:
        for base in roots:
            path = base / relative
            if path.is_file() and _has_flood_column(path):
                return path
    return None


def _has_flood_column(path: Path) -> bool:
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            header = handle.readline().casefold()
    except OSError:
        return False
    return "flood" in header and "date" in header and "township" in header
