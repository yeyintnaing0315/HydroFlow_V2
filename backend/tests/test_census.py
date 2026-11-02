from fastapi.testclient import TestClient

from app.main import app
from app.services.census import load_census, township_profile

client = TestClient(app)


def test_census_reference_matches_bago_workbook_totals() -> None:
    census = load_census()

    assert census.population.total.total == 4_453_687
    assert census.population.total.male + census.population.total.female == 4_453_687
    assert census.population.urban.total + census.population.rural.total == 4_453_687
    assert census.households.total == 1_029_962
    assert census.households.urban_dwellings.total + census.households.rural_dwellings.total == 1_029_962
    assert len(census.districts) == 6
    assert sum(len(district.townships) for district in census.districts) == 28
    assert sum(group.total.total for group in census.age_groups) == 4_453_687
    assert census.age_groups[0].label == "0-4"
    assert census.age_groups[-1].label == "90+"

    district, township = township_profile("Bago")
    assert district is not None and township is not None
    assert district.name_en == "Bago"
    assert township.population.total == 484_994
    assert township.households.total == 111_465
    assert sum(group.total.total for group in district.age_groups) == district.population.total


def test_census_endpoint_serves_the_reference() -> None:
    response = client.get("/census")

    assert response.status_code == 200
    body = response.json()
    assert body["census_year"] == 2024
    assert body["population"]["total"]["total"] == 4_453_687
    assert body["districts"][0]["name_en"] == "Bago"


def test_missing_census_file_is_unavailable(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CENSUS_PATH", str(tmp_path / "missing.json"))
    load_census.cache_clear()
    try:
        response = client.get("/census")
        assert response.status_code == 503
    finally:
        load_census.cache_clear()
