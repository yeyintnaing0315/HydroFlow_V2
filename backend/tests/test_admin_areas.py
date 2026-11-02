import json
from datetime import date
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.services import geography

CROSSWALK = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "external"
    / "geography"
    / "bago_district_crosswalk_2022.json"
)


def _feature(level: int, code: str, name: str, parents: dict[int, str]):
    properties = {
        "adm1_pcode": parents.get(1, code if level == 1 else "MMR007"),
        "adm1_name": "Bago",
        "valid_on": "2024-02-15",
        "version": "v01",
        "center_lat": 18 + level / 100,
        "center_lon": 96 + level / 100,
    }
    for parent_level, parent_code in parents.items():
        properties[f"adm{parent_level}_pcode"] = parent_code
        properties[f"adm{parent_level}_name"] = f"Parent {parent_code}"
    properties[f"adm{level}_pcode"] = code
    properties[f"adm{level}_name"] = name
    return {
        "type": "Feature",
        "properties": properties,
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[96, 18], [96.1, 18], [96.1, 18.1], [96, 18.1], [96, 18]]],
        },
    }


def test_imported_bago_hierarchy_has_verified_counts_and_parents(tmp_path) -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    features = [_feature(1, "MMR007", "Bago", {})]
    township_number = 0
    for district_number in range(6):
        district_code = f"MMR007D{district_number + 1:03d}"
        features.append(_feature(2, district_code, f"District {district_number}", {1: "MMR007"}))
        township_count = 5 if district_number < 4 else 4
        for _ in range(township_count):
            township_number += 1
            features.append(
                _feature(
                    3,
                    f"MMR007{township_number:03d}",
                    f"Township {township_number}",
                    {1: "MMR007", 2: district_code},
                )
            )
    path = tmp_path / "bago.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8")

    counts = [5, 5, 5, 5, 4, 4]
    districts = []
    next_township = 1
    for district_number, count in enumerate(counts):
        districts.append(
            {
                "id": f"MMR007D{district_number + 1:03d}",
                "name_en": f"District {district_number}",
                "townships": [f"Township {n}" for n in range(next_township, next_township + count)],
            }
        )
        next_township += count
    crosswalk = tmp_path / "crosswalk.json"
    crosswalk.write_text(
        json.dumps({"region": {"id": "MMR-BAGO", "name_en": "Bago"}, "districts": districts}),
        encoding="utf-8",
    )
    with Session(engine) as session:
        counts = geography.import_ocha_geojson(session, [path], district_crosswalk=crosswalk)
        assert counts["region"] == 1
        assert counts["district"] == 6
        assert counts["township"] == 28
        payload = geography.bago_area_response(session)
        assert payload["dataset_version"] == geography.OCHA_VERSION
        assert len(payload["districts"]) == 6
        assert sum(len(row["townships"]) for row in payload["districts"]) == 28
        assert payload["districts"][0]["geometry"]["type"] in {"Polygon", "MultiPolygon"}


def test_import_rejects_incomplete_district_coverage(tmp_path) -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    path = tmp_path / "incomplete.geojson"
    path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    _feature(1, "MMR007", "Bago", {}),
                    _feature(2, "MMR007D001", "Only district", {1: "MMR007"}),
                ],
            }
        ),
        encoding="utf-8",
    )
    with Session(engine) as session:
        try:
            geography.import_ocha_geojson(session, [path], district_crosswalk=CROSSWALK)
        except ValueError as exc:
            assert "six Bago districts" in str(exc) or "crosswalk" in str(exc).lower()
        else:
            raise AssertionError("incomplete geography must fail validation")
