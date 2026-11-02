import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.api import RoutePlanRequest, RouteStop
from app.services import clients, kardinal

client = TestClient(app)


def _request() -> dict:
    return {
        "origin": {"id": "bago", "name": "Bago", "latitude": 17.336, "longitude": 96.481},
        "stops": [
            {"id": "kawa", "name": "Kawa", "latitude": 17.0, "longitude": 96.5},
            {"id": "waw", "name": "Waw", "latitude": 17.5, "longitude": 96.7},
        ],
        "vehicle_profile": "car",
        "service_minutes": 15,
        "return_to_origin": True,
    }


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self.payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://app.kardinal.ai/api/v2/plans")
            response = httpx.Response(self.status_code, json=self.payload, request=request)
            raise httpx.HTTPStatusError("error", request=request, response=response)

    def json(self) -> dict:
        return self.payload


class FakeKardinal:
    def __init__(self, solution: dict | None = None, fail_status: int | None = None):
        self.solution = solution or {
            "item": {
                "agencyId": "BLD0215370_production",
                "unaffectedStopIds": [],
                "tours": [
                    {
                        "resourceId": "relief-vehicle",
                        "distanceInKm": 42.5,
                        "workingDuration": "PT1H20M",
                        "wayPoints": [
                            {
                                "type": "stop",
                                "stopId": "waw",
                                "arrivalTime": "2026-10-15T03:00:00Z",
                                "stopKind": "delivery",
                            },
                            {
                                "type": "stop",
                                "stopId": "kawa",
                                "arrivalTime": "2026-10-15T04:10:00Z",
                                "stopKind": "delivery",
                            },
                        ],
                    }
                ],
            }
        }
        self.fail_status = fail_status
        self.calls: list[tuple[str, str, dict]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def post(self, url: str, **kwargs) -> FakeResponse:
        self.calls.append(("POST", url, kwargs))
        if self.fail_status:
            return FakeResponse({"message": "rejected"}, self.fail_status)
        return FakeResponse({"item": {"id": "plan-1"}})

    async def get(self, url: str, **kwargs) -> FakeResponse:
        self.calls.append(("GET", url, kwargs))
        if url.endswith("/state"):
            return FakeResponse({"item": {"state": "optimized"}})
        return FakeResponse(self.solution)

    async def delete(self, url: str, **kwargs) -> FakeResponse:
        self.calls.append(("DELETE", url, kwargs))
        return FakeResponse({})


def test_route_orders_stops_and_hides_the_key(monkeypatch) -> None:
    fake = FakeKardinal()
    monkeypatch.setenv("KARDINAL_API_KEY", "test-kardinal-token")
    monkeypatch.setattr(clients, "_load_project_env", lambda: None)
    monkeypatch.setattr(kardinal.httpx, "AsyncClient", lambda **kwargs: fake)

    response = client.post("/routes", json=_request())

    assert response.status_code == 200
    body = response.json()
    assert body["plan_id"] == "plan-1"
    assert body["state"] == "optimized"
    assert body["distance_km"] == 42.5
    assert body["duration"] == "PT1H20M"
    assert body["duration_minutes"] == 80
    assert [point["stop_id"] for point in body["waypoints"]] == ["waw", "kawa"]
    assert body["path"][0]["latitude"] == 17.336
    assert body["path"][-1]["latitude"] == 17.336
    assert "test-kardinal-token" not in response.text
    assert any("vehicleProfile.type is car" in note for note in body["assumptions"])
    methods = [call[0] for call in fake.calls]
    assert methods == ["POST", "GET", "GET", "DELETE"]
    posted = fake.calls[0][2]["json"]
    assert posted["resources"][0]["vehicleProfile"] == {"type": "car"}
    assert posted["resources"][0]["departure"] == {"lat": 17.336, "lon": 96.481}
    assert posted["orders"][0]["stops"][0]["kind"] == "delivery"
    assert fake.calls[0][2]["headers"]["Authorization"] == "Bearer test-kardinal-token"


def test_route_reports_a_missing_key(monkeypatch) -> None:
    monkeypatch.delenv("KARDINAL_API_KEY", raising=False)
    monkeypatch.setattr(clients, "_load_project_env", lambda: None)
    response = client.post("/routes", json=_request())
    assert response.status_code == 503
    assert response.json()["detail"] == "KARDINAL_API_KEY is not set"


def test_route_redacts_the_key_from_provider_errors(monkeypatch) -> None:
    fake = FakeKardinal(fail_status=401)
    monkeypatch.setenv("KARDINAL_API_KEY", "test-kardinal-token")
    monkeypatch.setattr(clients, "_load_project_env", lambda: None)
    monkeypatch.setattr(kardinal.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post("/routes", json=_request())
    assert response.status_code == 502
    assert "test-kardinal-token" not in response.text
    assert "401" in response.json()["detail"]


def test_route_rejects_the_origin_as_a_stop() -> None:
    payload = _request()
    payload["stops"][0]["id"] = "bago"
    response = client.post("/routes", json=payload)
    assert response.status_code == 422
    assert response.json()["detail"] == "Origin cannot also be a delivery stop"


def test_build_plan_records_an_open_fly_tour() -> None:
    data = RoutePlanRequest(
        origin=RouteStop(id="bago", name="Bago", latitude=17.336, longitude=96.481),
        stops=[RouteStop(id="kawa", name="Kawa", latitude=17.0, longitude=96.5)],
        vehicle_profile="fly",
        service_minutes=0,
        return_to_origin=False,
    )
    payload, assumptions = kardinal.build_plan(data)
    assert payload["resources"][0]["vehicleProfile"] == {"type": "fly", "kmph": 30}
    assert "arrival" not in payload["resources"][0]
    assert "operationDuration" not in payload["orders"][0]["stops"][0]
    assert any("straight-line" in note for note in assumptions)
    assert any("operationDuration was not set" in note for note in assumptions)
