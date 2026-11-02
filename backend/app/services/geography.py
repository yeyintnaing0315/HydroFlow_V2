from __future__ import annotations

import hashlib
import json
import csv
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import AdminAlias, AdminArea, DataSource, DatasetVersion, Settlement
from app.services.sources import ensure_sources

BAGO_PCODE = "MMR-BAGO"
BAGO_SOURCE_CODES = {"MMR007", "MMR008"}
OCHA_VERSION = "COD-AB-v01-2024-02-15"
LEVEL_TYPES = {1: "region", 2: "district", 3: "township", 4: "town_or_village_tract", 5: "urban_area"}


class GeographyUnavailableError(RuntimeError):
    pass


def _parse_date(value: object) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _number(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _geometry_bounds(geometry: dict[str, Any]) -> tuple[float, float, float, float]:
    if geometry.get("type") not in {"Polygon", "MultiPolygon", "Point"}:
        raise ValueError(f"Unsupported geometry type {geometry.get('type')}")
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
    if any(not (-180 <= longitude <= 180 and -90 <= latitude <= 90) for longitude, latitude in points):
        raise ValueError("Geometry contains an invalid WGS84 coordinate")
    return (
        min(point[0] for point in points),
        min(point[1] for point in points),
        max(point[0] for point in points),
        max(point[1] for point in points),
    )


def _feature_level(properties: dict[str, Any]) -> int:
    for level in range(5, 0, -1):
        if properties.get(f"adm{level}_pcode"):
            return level
    raise ValueError("Feature has no administrative PCode")


def _iter_features(paths: Iterable[Path]) -> Iterable[dict[str, Any]]:
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("type") != "FeatureCollection" or not isinstance(payload.get("features"), list):
            raise ValueError(f"{path} is not a GeoJSON FeatureCollection")
        yield from payload["features"]


def _checksum(paths: Iterable[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _name_key(value: object) -> str:
    aliases = {
        "phyu": "pyu",
        "okpho": "okpo",
        "paukkhaung": "paukkaung",
        "pandaung": "padaung",
        "tharrawaddy": "thayarwady",
    }
    key = "".join(character for character in str(value).casefold() if character.isalnum())
    return aliases.get(key, key)


def _merge_polygon_geometries(features: list[dict[str, Any]]) -> dict[str, Any]:
    polygons: list[Any] = []
    for feature in features:
        geometry = feature.get("geometry") or {}
        if geometry.get("type") == "Polygon":
            polygons.append(geometry.get("coordinates"))
        elif geometry.get("type") == "MultiPolygon":
            polygons.extend(geometry.get("coordinates") or [])
    if not polygons:
        raise ValueError("Cannot derive a boundary without township polygon geometry")
    return {"type": "MultiPolygon", "coordinates": polygons}


def _derived_feature(
    level: int,
    code: str,
    name_en: str,
    name_local: str,
    parent_code: str | None,
    township_features: list[dict[str, Any]],
) -> dict[str, Any]:
    latitudes = [_number(item["properties"].get("center_lat")) for item in township_features]
    longitudes = [_number(item["properties"].get("center_lon")) for item in township_features]
    if any(value is None for value in (*latitudes, *longitudes)):
        raise ValueError(f"Cannot derive {name_en}: township centroid missing")
    properties: dict[str, Any] = {
        f"adm{level}_pcode": code,
        f"adm{level}_name": name_en,
        f"adm{level}_name1": name_local,
        "center_lat": sum(latitudes) / len(latitudes),
        "center_lon": sum(longitudes) / len(longitudes),
        "area_sqkm": sum(
            _number(item["properties"].get("area_sqkm")) or 0 for item in township_features
        ),
        "valid_on": "2022-04-30",
    }
    if parent_code:
        properties[f"adm{level - 1}_pcode"] = parent_code
    return {
        "type": "Feature",
        "properties": properties,
        "geometry": _merge_polygon_geometries(township_features),
    }


def _apply_current_district_crosswalk(
    features: list[tuple[int, dict[str, Any]]],
    crosswalk_path: Path,
) -> list[tuple[int, dict[str, Any]]]:
    crosswalk = json.loads(Path(crosswalk_path).read_text(encoding="utf-8"))
    township_by_code: dict[str, dict[str, Any]] = {}
    for level, feature in features:
        if level != 3:
            continue
        code = str(feature["properties"]["adm3_pcode"])
        geometry_type = (feature.get("geometry") or {}).get("type")
        existing_type = (township_by_code.get(code, {}).get("geometry") or {}).get("type")
        if code not in township_by_code or (
            geometry_type in {"Polygon", "MultiPolygon"}
            and existing_type not in {"Polygon", "MultiPolygon"}
        ):
            township_by_code[code] = feature
    townships = list(township_by_code.values())
    by_name = {
        _name_key(feature["properties"].get("adm3_name")): feature for feature in townships
    }
    used: set[str] = set()
    derived_districts: list[dict[str, Any]] = []
    district_for_township: dict[str, dict[str, Any]] = {}
    for district in crosswalk.get("districts", []):
        members = []
        for name in district.get("townships", []):
            key = _name_key(name)
            feature = by_name.get(key)
            if feature is None:
                raise ValueError(f"District crosswalk township is absent from COD-AB: {name}")
            if key in used:
                raise ValueError(f"Township appears in more than one district: {name}")
            used.add(key)
            members.append(feature)
            district_for_township[str(feature["properties"]["adm3_pcode"])] = district
        derived_districts.append(
            _derived_feature(
                2,
                str(district["id"]),
                str(district["name_en"]),
                str(district.get("name_local") or ""),
                BAGO_PCODE,
                members,
            )
        )
    if used != set(by_name):
        missing = sorted(set(by_name) - used)
        raise ValueError(f"District crosswalk does not cover COD-AB townships: {missing}")

    canonical_townships = []
    for feature in townships:
        copied = {
            **feature,
            "properties": dict(feature["properties"]),
        }
        district = district_for_township[str(copied["properties"]["adm3_pcode"])]
        copied["properties"]["adm2_pcode"] = str(district["id"])
        copied["properties"]["adm2_name"] = str(district["name_en"])
        copied["properties"]["adm1_pcode"] = BAGO_PCODE
        canonical_townships.append(copied)

    region = crosswalk["region"]
    canonical_region = _derived_feature(
        1,
        str(region["id"]),
        str(region["name_en"]),
        str(region.get("name_local") or ""),
        None,
        townships,
    )
    descendants = []
    for level, feature in features:
        if level < 4:
            continue
        copied = {**feature, "properties": dict(feature["properties"])}
        copied["properties"]["adm1_pcode"] = BAGO_PCODE
        descendants.append((level, copied))
    return (
        [(1, canonical_region)]
        + [(2, feature) for feature in derived_districts]
        + [(3, feature) for feature in canonical_townships]
        + descendants
    )


def import_ocha_geojson(
    session: Session,
    paths: Iterable[Path],
    replace: bool = False,
    district_crosswalk: Path | None = None,
) -> dict[str, int]:
    """Import Bago COD-AB features while retaining source version and caveats."""
    files = [Path(path) for path in paths]
    if not files or any(not path.is_file() for path in files):
        raise FileNotFoundError("One or more COD-AB GeoJSON files are missing")
    if district_crosswalk is None:
        district_crosswalk = default_district_crosswalk()
    if not Path(district_crosswalk).is_file():
        raise FileNotFoundError("A provenance-recorded current-district crosswalk is required")
    district_crosswalk = Path(district_crosswalk)
    incoming_checksum = _checksum([*files, district_crosswalk])

    source = ensure_sources(session)["ocha_cod_ab"]
    version = session.scalar(
        select(DatasetVersion).where(
            DatasetVersion.source_id == source.id,
            DatasetVersion.version == OCHA_VERSION,
        )
    )
    if version is None:
        version = DatasetVersion(
            source_id=source.id,
            version=OCHA_VERSION,
            valid_from=date(2024, 2, 15),
            retrieved_at=datetime.now(timezone.utc),
            checksum=incoming_checksum,
            source_url="https://data.humdata.org/dataset/cod-ab-mmr",
            metadata_json={
                "license": "CC BY 3.0 IGO",
                "coverage": "Admin 4 and 5 are partial",
                "caveat": "Source documents known, uncorrected errors.",
                "district_crosswalk": str(district_crosswalk.name),
            },
        )
        session.add(version)
        session.flush()
    elif version.checksum != incoming_checksum:
        raise ValueError(
            "Imported files do not match the immutable checksum for this dataset version"
        )
    elif replace:
        raise ValueError(
            "Imported dataset versions are immutable; use a new version instead of replacing "
            "stable administrative identifiers"
        )
    elif session.scalar(
        select(func.count()).select_from(AdminArea).where(AdminArea.dataset_version_id == version.id)
    ):
        return validate_bago_geography(session, version.id)

    features: list[tuple[int, dict[str, Any]]] = []
    for feature in _iter_features(files):
        properties = feature.get("properties") or {}
        level = _feature_level(properties)
        if properties.get("adm1_pcode") not in BAGO_SOURCE_CODES:
            continue
        features.append((level, feature))
    features = _apply_current_district_crosswalk(features, district_crosswalk)

    areas: dict[str, AdminArea] = {}
    for level, feature in sorted(features, key=lambda item: item[0]):
        properties = feature["properties"]
        source_code = str(properties[f"adm{level}_pcode"])
        if source_code in areas:
            continue
        parent_code = str(properties.get(f"adm{level - 1}_pcode") or "") if level > 1 else ""
        parent = areas.get(parent_code)
        area = AdminArea(
            dataset_version_id=version.id,
            parent_id=parent.id if parent else None,
            source_code=source_code,
            level=level,
            area_type=LEVEL_TYPES[level],
            name_en=str(properties.get(f"adm{level}_name") or source_code),
            name_local=properties.get(f"adm{level}_name1"),
            centroid_latitude=_number(properties.get("center_lat")),
            centroid_longitude=_number(properties.get("center_lon")),
            geometry_json=feature.get("geometry"),
            area_sq_km=_number(properties.get("area_sqkm")),
            coverage_status="partial" if level >= 4 else "complete",
            valid_from=_parse_date(properties.get("valid_on")),
            valid_to=_parse_date(properties.get("valid_to")),
        )
        session.add(area)
        session.flush()
        areas[source_code] = area
        session.add(AdminAlias(admin_area_id=area.id, namespace="pcode", alias=source_code))
    session.commit()
    return validate_bago_geography(session, version.id)


def import_mimu_v97(
    session: Session,
    paths: Iterable[Path],
    permission_reference: str,
) -> dict[str, int]:
    """Permission-gated importer for future MIMU v9.7 admin/village GeoJSON exports."""
    if not permission_reference.strip():
        raise PermissionError("A signed MIMU web-use permission reference is required")
    files = [Path(path) for path in paths]
    if not files or any(not path.is_file() for path in files):
        raise FileNotFoundError("One or more MIMU v9.7 GeoJSON files are missing")
    source = ensure_sources(session)["mimu_pcode"]
    source.enabled = True
    source.unavailable_reason = None
    source.metadata_json = {"web_permission_reference": permission_reference.strip()}
    version = session.scalar(
        select(DatasetVersion).where(
            DatasetVersion.source_id == source.id,
            DatasetVersion.version == "MIMU-PCode-v9.7-Jan2026",
        )
    )
    if version is None:
        version = DatasetVersion(
            source_id=source.id,
            version="MIMU-PCode-v9.7-Jan2026",
            valid_from=date(2026, 1, 22),
            retrieved_at=datetime.now(timezone.utc),
            checksum=_checksum(files),
            source_url="https://themimu.info/place-codes",
            metadata_json={"web_permission_reference": permission_reference.strip()},
        )
        session.add(version)
        session.flush()
    existing = {
        row.source_code: row
        for row in session.scalars(
            select(AdminArea).where(AdminArea.dataset_version_id == version.id)
        ).all()
    }
    features = list(_iter_features(files))
    area_rows: list[tuple[int, dict[str, Any]]] = []
    village_rows: list[dict[str, Any]] = []
    for feature in features:
        props = feature.get("properties") or {}
        if props.get("ST_PCODE") not in BAGO_SOURCE_CODES:
            continue
        if props.get("VLG_PCODE"):
            village_rows.append(feature)
            continue
        for level, prefix in ((4, "VT"), (3, "TS"), (2, "DT"), (1, "ST")):
            if props.get(f"{prefix}_PCODE"):
                area_rows.append((level, feature))
                break
    prefix_by_level = {1: "ST", 2: "DT", 3: "TS", 4: "VT"}
    for level, feature in sorted(area_rows, key=lambda item: item[0]):
        props = feature["properties"]
        prefix = prefix_by_level[level]
        code = str(props[f"{prefix}_PCODE"])
        if code in existing:
            continue
        parent_prefix = prefix_by_level.get(level - 1)
        parent = existing.get(str(props.get(f"{parent_prefix}_PCODE"))) if parent_prefix else None
        geometry = feature.get("geometry")
        latitude, longitude = _feature_point(props, geometry)
        area = AdminArea(
            dataset_version_id=version.id,
            parent_id=parent.id if parent else None,
            source_code=code,
            level=level,
            area_type=LEVEL_TYPES[level],
            name_en=str(props.get(prefix) or props.get(f"{prefix}_ENG") or code),
            name_local=props.get(f"{prefix}_MMR"),
            centroid_latitude=latitude,
            centroid_longitude=longitude,
            geometry_json=geometry,
            coverage_status="complete",
            valid_from=date(2026, 1, 22),
        )
        session.add(area)
        session.flush()
        existing[code] = area
        session.add(AdminAlias(admin_area_id=area.id, namespace="mimu_pcode", alias=code))
    settlement_count = 0
    for feature in village_rows:
        props = feature["properties"]
        code = str(props["VLG_PCODE"])
        if session.scalar(
            select(Settlement).where(
                Settlement.dataset_version_id == version.id,
                Settlement.source_code == code,
            )
        ):
            continue
        latitude, longitude = _feature_point(props, feature.get("geometry"))
        if latitude is None or longitude is None:
            raise ValueError(f"MIMU village {code} has no verified coordinate")
        parent = existing.get(str(props.get("VT_PCODE") or props.get("TS_PCODE")))
        session.add(
            Settlement(
                dataset_version_id=version.id,
                admin_area_id=parent.id if parent else None,
                source_code=code,
                name_en=str(props.get("VILLAGE") or code),
                name_local=props.get("VLG_MMR"),
                settlement_type="village",
                latitude=latitude,
                longitude=longitude,
                verification_status="mimu_v9.7_source",
                metadata_json={"permission_reference": permission_reference.strip()},
            )
        )
        settlement_count += 1
    session.flush()
    counts = validate_bago_geography(session, version.id)
    session.commit()
    return {
        "administrative_areas": sum(counts.values()),
        "settlements_imported": settlement_count,
    }


def import_relief_aliases(session: Session, path: Path) -> dict[str, Any]:
    """Link legacy relief slugs to stable imported township PCodes by verified names."""
    version, source = latest_dataset(session)
    version_id = version.id
    townships = session.scalars(
        select(AdminArea).where(
            AdminArea.dataset_version_id == version_id,
            AdminArea.level == 3,
        )
    ).all()
    by_name = {_name_key(row.name_en): row for row in townships}
    pairs: set[tuple[str, str]] = set()
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        for payload in csv.DictReader(handle):
            slug = str(payload.get("township_id") or "").strip()
            name = str(payload.get("township") or "").strip()
            if slug and name:
                pairs.add((slug, name))
    existing = {
        row.alias: row
        for row in session.scalars(
            select(AdminAlias).where(AdminAlias.namespace == "relief_slug")
        ).all()
    }
    added = 0
    updated = 0
    unresolved: list[dict[str, str]] = []
    for slug, name in sorted(pairs):
        area = by_name.get(_name_key(name))
        if area is None:
            unresolved.append({"township_id": slug, "name": name})
            continue
        exists = existing.get(slug)
        if exists:
            if exists.admin_area_id != area.id:
                previous = session.get(AdminArea, exists.admin_area_id)
                if previous is None or _name_key(previous.name_en) != _name_key(area.name_en):
                    raise ValueError(f"Relief alias {slug} maps to multiple townships")
                exists.admin_area_id = area.id
                updated += 1
            continue
        alias = AdminAlias(admin_area_id=area.id, namespace="relief_slug", alias=slug)
        session.add(alias)
        existing[slug] = alias
        added += 1
    session.commit()
    return {"aliases_added": added, "aliases_updated": updated, "unresolved": unresolved}


def relief_slug_for_area(session: Session, source_code: str) -> str | None:
    return session.scalar(
        select(AdminAlias.alias)
        .join(AdminArea, AdminAlias.admin_area_id == AdminArea.id)
        .where(
            AdminArea.source_code == source_code,
            AdminAlias.namespace == "relief_slug",
        )
    )


def _feature_point(
    properties: dict[str, Any],
    geometry: dict[str, Any] | None,
) -> tuple[float | None, float | None]:
    latitude = _number(properties.get("Latitude") or properties.get("center_lat"))
    longitude = _number(properties.get("Longitude") or properties.get("center_lon"))
    if (
        (latitude is None or longitude is None)
        and geometry
        and geometry.get("type") == "Point"
    ):
        coordinates = geometry.get("coordinates") or []
        if len(coordinates) >= 2:
            longitude, latitude = float(coordinates[0]), float(coordinates[1])
    return latitude, longitude


def default_district_crosswalk() -> Path:
    here = Path(__file__).resolve()
    candidates = (
        here.parents[3] / "data" / "external" / "geography" / "bago_district_crosswalk_2022.json",
        here.parents[2] / "data" / "external" / "geography" / "bago_district_crosswalk_2022.json",
        Path("/app/data/external/geography/bago_district_crosswalk_2022.json"),
        Path("/data/geography/bago_district_crosswalk_2022.json"),
    )
    for path in candidates:
        if path.is_file():
            return path
    return candidates[0]


def validate_bago_geography(session: Session, dataset_version_id: int | None = None) -> dict[str, int]:
    if dataset_version_id is None:
        dataset_version_id = latest_dataset_id(session)
    rows = session.scalars(
        select(AdminArea).where(AdminArea.dataset_version_id == dataset_version_id)
    ).all()
    counts = {level: sum(row.level == level for row in rows) for level in range(1, 6)}
    if counts[1] != 1:
        raise ValueError(f"Expected one Bago region, found {counts[1]}")
    if counts[2] != 6:
        raise ValueError(f"Expected six Bago districts, found {counts[2]}")
    if counts[3] != 28:
        raise ValueError(f"Expected 28 Bago townships, found {counts[3]}")
    by_id = {row.id: row for row in rows}
    bounds_by_id: dict[int, tuple[float, float, float, float]] = {}
    for row in rows:
        if row.level > 1 and (row.parent_id not in by_id or by_id[row.parent_id].level != row.level - 1):
            raise ValueError(f"Invalid parent link for {row.source_code}")
        if row.centroid_latitude is not None and not -90 <= row.centroid_latitude <= 90:
            raise ValueError(f"Invalid latitude for {row.source_code}")
        if row.centroid_longitude is not None and not -180 <= row.centroid_longitude <= 180:
            raise ValueError(f"Invalid longitude for {row.source_code}")
        if row.geometry_json is not None:
            bounds = _geometry_bounds(row.geometry_json)
            bounds_by_id[row.id] = bounds
            if (
                row.centroid_latitude is not None
                and row.centroid_longitude is not None
                and not (
                    bounds[0] <= row.centroid_longitude <= bounds[2]
                    and bounds[1] <= row.centroid_latitude <= bounds[3]
                )
            ):
                raise ValueError(f"Centroid lies outside geometry for {row.source_code}")
    for row in rows:
        parent_bounds = bounds_by_id.get(row.parent_id)
        if (
            parent_bounds
            and row.centroid_latitude is not None
            and row.centroid_longitude is not None
            and not (
                parent_bounds[0] <= row.centroid_longitude <= parent_bounds[2]
                and parent_bounds[1] <= row.centroid_latitude <= parent_bounds[3]
            )
        ):
            raise ValueError(f"{row.source_code} centroid lies outside parent bounds")
    return {LEVEL_TYPES[level]: count for level, count in counts.items()}


def latest_dataset(session: Session) -> tuple[DatasetVersion, DataSource]:
    ensure_sources(session)
    result = session.execute(
        select(DatasetVersion, DataSource)
        .join(DataSource, DatasetVersion.source_id == DataSource.id)
        .where(
            DataSource.kind == "administrative-geography",
            DataSource.enabled.is_(True),
        )
        .order_by(DatasetVersion.valid_from.desc(), DatasetVersion.retrieved_at.desc())
        .limit(1)
    ).first()
    if result is None:
        raise GeographyUnavailableError("No licensed Bago geography has been imported")
    return result[0], result[1]


def latest_dataset_id(session: Session) -> int:
    return latest_dataset(session)[0].id


def hierarchy(
    session: Session,
    max_level: int = 5,
    query: str | None = None,
    include_geometry: bool = False,
) -> dict[str, Any]:
    version, source = latest_dataset(session)
    version_id = version.id
    statement = (
        select(AdminArea)
        .where(AdminArea.dataset_version_id == version_id, AdminArea.level <= max_level)
        .order_by(AdminArea.level, AdminArea.name_en)
    )
    if query:
        term = f"%{query.strip()}%"
        statement = statement.where(
            or_(
                AdminArea.name_en.ilike(term),
                AdminArea.name_local.ilike(term),
                AdminArea.source_code.ilike(term),
            )
        )
    rows = session.scalars(statement).all()
    codes_by_id = dict(
        session.execute(
            select(AdminArea.id, AdminArea.source_code).where(
                AdminArea.dataset_version_id == version_id
            )
        ).all()
    )
    return {
        "source": source.name,
        "dataset_version": version.version,
        "license": source.license_name or "See source terms",
        "coverage_note": str(
            version.metadata_json.get("coverage")
            or version.metadata_json.get("caveat")
            or "Coverage follows the imported licensed dataset."
        ),
        "areas": [
            _area_dict(row, codes_by_id.get(row.parent_id), include_geometry) for row in rows
        ],
    }


def bago_area_response(session: Session) -> dict[str, Any]:
    version, source = latest_dataset(session)
    version_id = version.id
    rows = session.scalars(
        select(AdminArea)
        .where(AdminArea.dataset_version_id == version_id, AdminArea.level <= 3)
        .order_by(AdminArea.level, AdminArea.name_en)
    ).all()
    region = next((row for row in rows if row.level == 1), None)
    if region is None:
        raise GeographyUnavailableError("Imported dataset has no Bago region")
    districts = []
    for district in (row for row in rows if row.level == 2):
        townships = [_legacy_point(row) for row in rows if row.parent_id == district.id]
        districts.append({**_legacy_point(district), "townships": townships, "geometry": district.geometry_json})
    return {
        "source": source.name,
        "dataset_version": version.version,
        "license": source.license_name or "See source terms",
        "coverage_note": str(
            version.metadata_json.get("coverage")
            or version.metadata_json.get("caveat")
            or "Coverage follows the imported licensed dataset."
        ),
        "region_id": region.source_code,
        "region_name_en": region.name_en,
        "region_name_local": region.name_local or "",
        "latitude": region.centroid_latitude,
        "longitude": region.centroid_longitude,
        "geometry": region.geometry_json,
        "districts": districts,
    }


def _legacy_point(area: AdminArea) -> dict[str, Any]:
    if area.centroid_latitude is None or area.centroid_longitude is None:
        raise ValueError(f"{area.source_code} has no verified centroid")
    return {
        "id": area.source_code,
        "slug": area.source_code,
        "name_en": area.name_en,
        "name_local": area.name_local or "",
        "latitude": area.centroid_latitude,
        "longitude": area.centroid_longitude,
        "geometry": area.geometry_json,
        "level": area.level,
        "area_type": area.area_type,
        "coverage_status": area.coverage_status,
    }


def _area_dict(
    area: AdminArea,
    parent_code: str | None,
    include_geometry: bool,
) -> dict[str, Any]:
    return {
        "id": area.source_code,
        "parent_id": parent_code,
        "level": area.level,
        "area_type": area.area_type,
        "name_en": area.name_en,
        "name_local": area.name_local,
        "latitude": area.centroid_latitude,
        "longitude": area.centroid_longitude,
        "geometry": area.geometry_json,
        "coverage_status": area.coverage_status,
    }
