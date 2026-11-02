"""Bago Region districts and townships.

Coordinates come from Open Admin Data. Membership follows the six districts
created for Bago Region on 30 April 2022: Bago, Nyaunglebin, Taungoo,
Thayarwady, Nattalin, and Pyay. Nyaunglebin was split from Bago. Nattalin was
split from Pyay and Thayarwady. Later sub-townships published by Open Admin
Data are left out. Htantabin is not in that API under Bago; its centroid is
the OpenStreetMap boundary for Htantabin Township, Taungoo District
(relation 5996628).
"""

from __future__ import annotations

import asyncio
import json
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

API_ROOT = "https://api.openadmindata.org/api/v1/mm"
BAGO_REGION_ID = "MMR007"
BAGO_REGION_SLUG = "bago-MMR007"
TIMEOUT_SECONDS = 8.0
USER_AGENT = "HydroFlow/1.0 (academic flood-relief prototype)"

# name_en, name_local, id used when Open Admin Data has no district, townships.
# Order matches the six-district Bago Region list.
BAGO_DIVISION: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("Bago", "ပဲခူးခရိုင်", "MMR007D001", ("Bago", "Kawa", "Thanatpin", "Waw")),
    (
        "Nyaunglebin",
        "ညောင်လေးပင်ခရိုင်",
        "nyaunglebin",
        ("Nyaunglebin", "Kyauktaga", "Daik-U", "Shwegyin", "Kyaukkyi"),
    ),
    (
        "Taungoo",
        "တောင်ငူခရိုင်",
        "MMR007D002",
        ("Taungoo", "Oktwin", "Yedashe", "Pyu", "Htantabin"),
    ),
    (
        "Thayarwady",
        "သာယာဝတီခရိုင်",
        "MMR008D002",
        ("Thayarwady", "Letpadan", "Minhla", "Monyo", "Okpo", "Gyobingauk"),
    ),
    ("Nattalin", "နတ်တလင်းခရိုင်", "nattalin", ("Nattalin", "Zigon", "Thegon", "Paungde")),
    ("Pyay", "ပြည်ခရိုင်", "MMR008D001", ("Pyay", "Paukkaung", "Padaung", "Shwedaung")),
)
_NAME_ALIASES = {
    "phyu": "pyu",
    "paukkhaung": "paukkaung",
    "okpho": "okpo",
}
# OpenStreetMap relation 5996628: Htantabin Township, Taungoo District, Bago Region.
HTANTABIN_TOWNSHIP = {
    "id": "htantabin-taungoo",
    "slug": "htantabin-taungoo",
    "name_en": "Htantabin",
    "name_local": "ထန်းတပင်",
    "latitude": 18.736925,
    "longitude": 96.520799,
}

_cache: dict[str, Any] | None = None


def clear_cache() -> None:
    global _cache
    _cache = None
    _township_boundaries.cache_clear()


def _first_existing(*paths: Path) -> Path:
    for path in paths:
        if path.is_file():
            return path
    return paths[0]


def _boundary_path() -> Path:
    here = Path(__file__).resolve()
    return _first_existing(
        here.parents[3] / "data" / "external" / "geography" / "bago_township_boundaries.geojson",
        here.parents[2] / "data" / "external" / "geography" / "bago_township_boundaries.geojson",
        Path("/app/data/external/geography/bago_township_boundaries.geojson"),
        Path("/data/geography/bago_township_boundaries.geojson"),
    )


def _point(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(raw["id"]),
        "slug": str(raw["slug"]),
        "name_en": str(raw["name_en"]),
        "name_local": str(raw["name_local"]),
        "latitude": float(raw["lat"]),
        "longitude": float(raw["lon"]),
    }


async def _get(client: httpx.AsyncClient, path: str) -> dict[str, Any]:
    response = await client.get(f"{API_ROOT}/{path}")
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("Invalid Open Admin Data response")
    return payload


def _name_key(name: str) -> str:
    compact = "".join(character for character in name.casefold() if character.isalnum())
    return _NAME_ALIASES.get(compact, compact)


def _district_center(townships: list[dict[str, Any]]) -> tuple[float, float]:
    latitude = sum(item["latitude"] for item in townships) / len(townships)
    longitude = sum(item["longitude"] for item in townships) / len(townships)
    return latitude, longitude


def _geometry_centroid(geometry: dict[str, Any]) -> tuple[float, float]:
    points: list[tuple[float, float]] = []

    def collect(value: Any) -> None:
        if (
            isinstance(value, list)
            and len(value) >= 2
            and isinstance(value[0], (int, float))
            and isinstance(value[1], (int, float))
        ):
            points.append((float(value[0]), float(value[1])))
            return
        if isinstance(value, list):
            for item in value:
                collect(item)

    collect(geometry.get("coordinates"))
    if not points:
        raise ValueError("Geometry contains no coordinates")
    longitude = sum(point[0] for point in points) / len(points)
    latitude = sum(point[1] for point in points) / len(points)
    return latitude, longitude


@lru_cache(maxsize=1)
def _township_boundaries() -> dict[str, dict[str, Any]]:
    path = _boundary_path()
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    boundaries: dict[str, dict[str, Any]] = {}
    for feature in payload.get("features", []):
        name = str((feature.get("properties") or {}).get("name_en") or "")
        geometry = feature.get("geometry")
        if name and isinstance(geometry, dict):
            boundaries[_name_key(name)] = geometry
    return boundaries


def _as_multipolygon(geometries: list[dict[str, Any]]) -> dict[str, Any] | None:
    coordinates: list[Any] = []
    for geometry in geometries:
        kind = geometry.get("type")
        if kind == "Polygon":
            coordinates.append(geometry.get("coordinates"))
        elif kind == "MultiPolygon":
            coordinates.extend(geometry.get("coordinates") or [])
    if not coordinates:
        return None
    return {"type": "MultiPolygon", "coordinates": coordinates}


def _attach_boundaries(districts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    boundaries = _township_boundaries()
    if not boundaries:
        return districts
    for district in districts:
        township_geometries: list[dict[str, Any]] = []
        for township in district["townships"]:
            geometry = boundaries.get(_name_key(str(township["name_en"])))
            if geometry is None:
                continue
            township["geometry"] = geometry
            township_geometries.append(geometry)
        outline = _as_multipolygon(township_geometries)
        if outline is not None:
            district["geometry"] = outline
    return districts


def regroup_bago_districts(api_districts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Place the 28 Bago townships into the 2022 six districts."""
    districts_by_name = {_name_key(item["name_en"]): item for item in api_districts}
    townships_by_name = {
        _name_key(township["name_en"]): township
        for district in api_districts
        for township in district["townships"]
    }
    grouped: list[dict[str, Any]] = []
    for district_name, name_local, fallback_id, township_names in BAGO_DIVISION:
        townships: list[dict[str, Any]] = []
        for township_name in township_names:
            found = townships_by_name.get(_name_key(township_name))
            if found is None and _name_key(township_name) == "htantabin":
                townships.append(dict(HTANTABIN_TOWNSHIP))
                continue
            if found is None:
                raise ValueError(f"Open Admin Data is missing {township_name} Township")
            townships.append({**found, "name_en": township_name})
        source = districts_by_name.get(_name_key(district_name))
        latitude, longitude = _district_center(townships)
        if source is None:
            grouped.append(
                {
                    "id": fallback_id,
                    "slug": fallback_id,
                    "name_en": district_name,
                    "name_local": name_local,
                    "latitude": latitude,
                    "longitude": longitude,
                    "townships": townships,
                }
            )
            continue
        grouped.append(
            {
                **source,
                "name_en": district_name,
                "name_local": name_local,
                "latitude": latitude,
                "longitude": longitude,
                "townships": townships,
            }
        )
    return _attach_boundaries(grouped)


async def load_bago_admin(client: httpx.AsyncClient) -> dict[str, Any]:
    region = await _get(client, f"region/{quote(BAGO_REGION_SLUG)}.json")
    entity = region["entity"]
    if entity.get("id") != BAGO_REGION_ID or region.get("children", {}).get("level") != "district":
        raise ValueError("Open Admin Data did not return Bago Region districts")

    district_rows = [
        item
        for item in region["children"]["entities"]
        if item.get("parent_id") == BAGO_REGION_ID
    ]
    details = await asyncio.gather(
        *[_get(client, f"district/{quote(str(item['slug']))}.json") for item in district_rows]
    )

    districts: list[dict[str, Any]] = []
    for detail in details:
        district = detail["entity"]
        children = detail.get("children", {})
        if district.get("parent_id") != BAGO_REGION_ID or children.get("level") != "township":
            raise ValueError("Open Admin Data returned a non-Bago district")
        townships = [
            _point(item)
            for item in children["entities"]
            if item.get("parent_id") == district["id"]
        ]
        districts.append({**_point(district), "townships": townships})

    return {
        "source": "Open Admin Data",
        "dataset_version": "open-admin-data-live",
        "license": "Open Admin Data terms",
        "coverage_note": (
            "Township centroids from Open Admin Data. "
            "Boundary polygons are simplified geoBoundaries gbOpen Myanmar ADM3 "
            "outlines (CC BY 4.0), grouped into the 2022 districts."
        ),
        "region_id": BAGO_REGION_ID,
        "region_name_en": "Bago",
        "region_name_local": str(entity["name_local"]),
        "latitude": float(entity["lat"]),
        "longitude": float(entity["lon"]),
        "districts": regroup_bago_districts(districts),
    }


def _local_township(
    name_en: str,
    geometry: dict[str, Any],
    name_local: str | None = None,
) -> dict[str, Any]:
    latitude, longitude = _geometry_centroid(geometry)
    slug = _name_key(name_en)
    return {
        "id": slug,
        "slug": slug,
        "name_en": name_en,
        "name_local": name_local or name_en,
        "latitude": latitude,
        "longitude": longitude,
        "geometry": geometry,
    }


def local_bago_areas() -> dict[str, Any]:
    """Build the six 2022 districts from the bundled geoBoundaries polygons."""
    boundaries = _township_boundaries()
    if not boundaries:
        raise ValueError("Local Bago township boundaries are missing")
    districts: list[dict[str, Any]] = []
    for district_name, name_local, fallback_id, township_names in BAGO_DIVISION:
        townships: list[dict[str, Any]] = []
        for township_name in township_names:
            geometry = boundaries.get(_name_key(township_name))
            if geometry is None and _name_key(township_name) == "htantabin":
                townships.append(dict(HTANTABIN_TOWNSHIP))
                continue
            if geometry is None:
                raise ValueError(f"Local boundaries are missing {township_name} Township")
            extra_local = HTANTABIN_TOWNSHIP["name_local"] if _name_key(township_name) == "htantabin" else None
            townships.append(_local_township(township_name, geometry, extra_local))
        latitude, longitude = _district_center(townships)
        outline = _as_multipolygon(
            [item["geometry"] for item in townships if isinstance(item.get("geometry"), dict)]
        )
        districts.append(
            {
                "id": fallback_id,
                "slug": fallback_id,
                "name_en": district_name,
                "name_local": name_local,
                "latitude": latitude,
                "longitude": longitude,
                "geometry": outline,
                "townships": townships,
            }
        )
    all_townships = [township for district in districts for township in district["townships"]]
    region_outline = _as_multipolygon(
        [item["geometry"] for item in districts if isinstance(item.get("geometry"), dict)]
    )
    return {
        "source": "geoBoundaries gbOpen Myanmar ADM3",
        "dataset_version": "gbOpen-MMR-ADM3-local",
        "license": "CC BY 4.0",
        "coverage_note": (
            "Township polygons are bundled simplified geoBoundaries gbOpen Myanmar ADM3 "
            "outlines (CC BY 4.0), grouped into the 2022 districts. Open Admin Data and "
            "licensed OCHA COD-AB were unavailable."
        ),
        "region_id": BAGO_REGION_ID,
        "region_name_en": "Bago",
        "region_name_local": "ပဲခူးတိုင်းဒေသကြီး",
        "latitude": sum(item["latitude"] for item in all_townships) / len(all_townships),
        "longitude": sum(item["longitude"] for item in all_townships) / len(all_townships),
        "geometry": region_outline,
        "districts": districts,
    }


def bundled_bago_areas() -> dict[str, Any]:
    """Offline Bago districts/townships from bundled geoBoundaries polygons."""
    return local_bago_areas()


async def bago_areas() -> dict[str, Any]:
    global _cache
    if _cache is None:
        if _township_boundaries():
            try:
                _cache = local_bago_areas()
            except (KeyError, TypeError, ValueError):
                _cache = None
        if _cache is None:
            try:
                async with httpx.AsyncClient(
                    timeout=TIMEOUT_SECONDS,
                    follow_redirects=True,
                    headers={"User-Agent": USER_AGENT},
                ) as client:
                    _cache = await load_bago_admin(client)
            except (httpx.HTTPError, KeyError, TypeError, ValueError):
                _cache = local_bago_areas()
    return _cache
