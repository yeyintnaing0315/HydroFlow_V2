import asyncio

import httpx
from fastapi.testclient import TestClient

from app.schemas.api import BagoAreasResponse
from app.services import open_admin_areas


def test_local_boundaries_cover_six_districts_and_polygons() -> None:
    open_admin_areas.clear_cache()
    payload = open_admin_areas.local_bago_areas()
    assert payload["region_name_en"] == "Bago"
    assert len(payload["districts"]) == 6
    townships = [township for district in payload["districts"] for township in district["townships"]]
    assert len(townships) == 28
    assert {township["name_en"] for township in townships} >= {"Bago", "Htantabin", "Pyay"}
    assert all(township.get("geometry", {}).get("type") in {"Polygon", "MultiPolygon"} for township in townships)
    assert all(district.get("geometry", {}).get("type") == "MultiPolygon" for district in payload["districts"])
    BagoAreasResponse.model_validate(payload)


def test_bago_areas_uses_local_polygons_when_open_admin_is_down(monkeypatch) -> None:
    open_admin_areas.clear_cache()

    async def boom(*_args, **_kwargs):
        raise httpx.ConnectError("All connection attempts failed")

    monkeypatch.setattr(open_admin_areas, "load_bago_admin", boom)
    payload = asyncio.run(open_admin_areas.bago_areas())
    assert payload["dataset_version"] == "gbOpen-MMR-ADM3-local"
    assert payload["districts"][0]["townships"][0]["geometry"]["type"] in {"Polygon", "MultiPolygon"}


def test_bago_areas_endpoint_serves_local_boundaries_without_ocha(client: TestClient) -> None:
    open_admin_areas.clear_cache()
    response = client.get("/bago-areas")
    assert response.status_code == 200, response.text
    assert "All connection attempts failed" not in response.text


def test_bundled_bago_areas_never_calls_network() -> None:
    open_admin_areas.clear_cache()
    payload = open_admin_areas.bundled_bago_areas()
    assert payload["dataset_version"] == "gbOpen-MMR-ADM3-local"
    assert payload["districts"][0]["geometry"]["type"] == "MultiPolygon"
    assert payload["region_name_en"] == "Bago"
    assert len(payload["districts"]) == 6
    assert sum(len(district["townships"]) for district in payload["districts"]) == 28
    assert payload["districts"][0]["townships"][0]["geometry"]["type"] in {"Polygon", "MultiPolygon"}
