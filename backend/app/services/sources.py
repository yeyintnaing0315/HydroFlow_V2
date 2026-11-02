from __future__ import annotations

import os
from dataclasses import asdict, dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DataSource


@dataclass(frozen=True)
class SourceDefinition:
    key: str
    name: str
    kind: str
    url: str
    license_name: str | None
    license_url: str | None
    attribution: str
    enabled: bool
    unavailable_reason: str | None = None


def definitions() -> tuple[SourceDefinition, ...]:
    return (
        SourceDefinition(
            "ocha_cod_ab",
            "OCHA Myanmar COD-AB v01",
            "administrative-geography",
            "https://data.humdata.org/dataset/cod-ab-mmr",
            "CC BY 3.0 IGO",
            "https://creativecommons.org/licenses/by/3.0/igo/",
            "OCHA FISS; source MIMU v9.4",
            True,
        ),
        SourceDefinition(
            "mimu_pcode",
            "MIMU PCode v9.7",
            "administrative-geography",
            "https://themimu.info/place-codes",
            "MIMU Data License",
            "https://www.themimu.info/mimu-terms-conditions",
            "Myanmar Information Management Unit (MIMU)",
            False,
            "Written MIMU permission is required for online embedding.",
        ),
        SourceDefinition(
            "open_meteo",
            "Open-Meteo Forecast API",
            "weather-forecast",
            "https://open-meteo.com/",
            "CC BY 4.0 data; free API non-commercial only",
            "https://open-meteo.com/en/license",
            "Weather data by Open-Meteo.com",
            True,
        ),
        SourceDefinition(
            "open_meteo_flood",
            "Open-Meteo Flood API (GloFAS-derived)",
            "modeled-discharge",
            "https://open-meteo.com/en/docs/flood-api",
            "CC BY 4.0 data; free API non-commercial only",
            "https://open-meteo.com/en/license",
            "Modeled river discharge via Open-Meteo; not a measured gauge level",
            True,
        ),
        SourceDefinition(
            "jrc_flood_hazard",
            "JRC River Flood Hazard v2.1",
            "static-hazard",
            "https://data.jrc.ec.europa.eu/collection/floods",
            "CC BY 4.0",
            "https://creativecommons.org/licenses/by/4.0/",
            "Joint Research Centre (European Commission)",
            True,
        ),
        SourceDefinition(
            "glo30_hand",
            "Copernicus GLO-30 HAND",
            "terrain",
            "https://registry.opendata.aws/copernicus-dem/",
            "Copernicus DEM terms",
            "https://dataspace.copernicus.eu/",
            "Copernicus DEM derivatives on AWS",
            True,
        ),
        SourceDefinition(
            "hydrobasins",
            "HydroBASINS Asia",
            "hydrology-catchment",
            "https://www.hydrosheds.org/hydrobasins",
            "HydroSHEDS license",
            "https://www.hydrosheds.org/",
            "HydroSHEDS / USGS WWF",
            True,
        ),
        SourceDefinition(
            "cems_glofas",
            "CEMS GloFAS historical and forecast",
            "modeled-discharge",
            "https://ewds.climate.copernicus.eu/",
            "Copernicus CEMS terms",
            "https://ewds.climate.copernicus.eu/licences/terms-of-use-cems",
            "Copernicus Emergency Management Service",
            bool(os.getenv("CDSAPI_KEY")),
            None if os.getenv("CDSAPI_KEY") else "CDSAPI_KEY is not set.",
        ),
        SourceDefinition(
            "chirps_v3",
            "CHIRPS v3 rainfall",
            "historical-weather",
            "https://www.chc.ucsb.edu/data/chirps",
            "CHIRPS terms",
            "https://www.chc.ucsb.edu/data/chirps",
            "Climate Hazards Center, UC Santa Barbara",
            True,
        ),
        SourceDefinition(
            "esa_worldcover",
            "ESA WorldCover 2021",
            "land-cover",
            "https://esa-worldcover.org/",
            "CC BY 4.0",
            "https://creativecommons.org/licenses/by/4.0/",
            "European Space Agency",
            True,
        ),
        SourceDefinition(
            "nasa_power",
            "NASA POWER",
            "historical-weather",
            "https://power.larc.nasa.gov/",
            "NASA open data",
            "https://power.larc.nasa.gov/docs/methodology/data/",
            "NASA POWER",
            True,
        ),
        SourceDefinition(
            "dmh_myanmar",
            "Myanmar Department of Meteorology and Hydrology",
            "official-warning-and-gauge",
            "https://www.moezala.gov.mm/",
            None,
            None,
            "Myanmar DMH",
            False,
            "No documented, permitted machine-readable public feed is configured.",
        ),
        SourceDefinition(
            "copernicus_ewds",
            "Copernicus GloFAS EWDS",
            "modeled-discharge",
            "https://ewds.climate.copernicus.eu/",
            "Copernicus CEMS terms",
            "https://ewds.climate.copernicus.eu/licences/terms-of-use-cems",
            "Copernicus Emergency Management Service",
            bool(os.getenv("COPERNICUS_EWDS_URL")),
            None if os.getenv("COPERNICUS_EWDS_URL") else "Account and accepted dataset terms required.",
        ),
        SourceDefinition(
            "copernicus_gfm",
            "Copernicus Global Flood Monitoring",
            "observed-inundation",
            "https://global-flood.emergency.copernicus.eu/",
            "Copernicus CEMS terms",
            "https://ewds.climate.copernicus.eu/licences/terms-of-use-cems",
            "Copernicus Emergency Management Service",
            bool(os.getenv("COPERNICUS_GFM_TOKEN")),
            None if os.getenv("COPERNICUS_GFM_TOKEN") else "GFM account/token is required.",
        ),
        SourceDefinition(
            "unosat",
            "UNOSAT flood extents",
            "observed-inundation",
            "https://data.humdata.org/organization/un-operational-satellite-applications-programme-unosat",
            "Dataset-specific; 2024 Myanmar product is CC BY-SA",
            "https://creativecommons.org/licenses/by-sa/4.0/",
            "United Nations Satellite Centre (UNOSAT)",
            True,
        ),
        SourceDefinition(
            "worldpop",
            "WorldPop 100 m population",
            "population",
            "https://hub.worldpop.org/",
            "CC BY 4.0",
            "https://creativecommons.org/licenses/by/4.0/",
            "WorldPop",
            True,
        ),
        SourceDefinition(
            "opentopography",
            "OpenTopography Copernicus GLO-30",
            "terrain",
            "https://opentopography.org/",
            "Provider and Copernicus terms",
            "https://opentopography.org/terms",
            "OpenTopography and Copernicus DEM",
            bool(os.getenv("OPENTOPOGRAPHY_API_KEY")),
            None if os.getenv("OPENTOPOGRAPHY_API_KEY") else "OPENTOPOGRAPHY_API_KEY is not set.",
        ),
    )


def ensure_sources(session: Session) -> dict[str, DataSource]:
    existing = {
        row.key: row for row in session.scalars(select(DataSource)).all()
    }
    for item in definitions():
        row = existing.get(item.key)
        values = asdict(item)
        values["metadata_json"] = {}
        if row is None:
            row = DataSource(**values)
            session.add(row)
            existing[item.key] = row
        else:
            for key, value in values.items():
                setattr(row, key, value)
    session.commit()
    return existing


def source_status(session: Session) -> list[dict[str, object]]:
    rows = ensure_sources(session)
    return [
        {
            "key": item.key,
            "name": item.name,
            "kind": item.kind,
            "enabled": rows[item.key].enabled,
            "unavailable_reason": rows[item.key].unavailable_reason,
            "attribution": item.attribution,
            "license_name": item.license_name,
            "url": item.url,
        }
        for item in definitions()
    ]
