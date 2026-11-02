# Data provenance

## Approved starting source

HydroFlow V2 may import the existing file:

`D:\Ai_Project\Hydroflow\data\processed\daily.csv`

That source was assembled from:

- Bago Region relief workbooks used to mark reported flood days.
- Open-Meteo historical/reanalysis rainfall.
- GloFAS modeled river discharge through the Open-Meteo Flood API.

Live model outlooks use Open-Meteo forecast rainfall and GloFAS modeled
forecast discharge when CEMS GloFAS ensemble rows are not present in
`data/offline/flood_sources.sqlite`. NASA POWER is queried only for retrospective weather
charts; its soil wetness and humidity fields were removed from V2 model inputs
because they are not reliably available for future dates. OpenTopography
Copernicus GLO-30 supplies display-only elevation. API keys live in `.env` and
are not written into source, logs, or responses. Route ordering uses Kardinal.

## 2010-present offline rebuild

Hindcast dates from **2010-01-01** use merged local hydrology in
`data/offline/flood_sources.sqlite` (Open-Meteo archive + GloFAS discharge),
optional **CHIRPS v3** (ClimateSERV), **CEMS GloFAS** (CDS/EWDS when configured),
and static **JRC flood hazard v2.1**, **GLO-30 HAND**, **HydroBASINS**, and
**ESA WorldCover** summaries under `data/external/rasters/` (via
`ml/flood/ingest_rasters.py`). **Copernicus GFM** is validation-only when
`COPERNICUS_GFM_TOKEN` is set. Supervised flood labels remain on the relief
archive from 2021 onward.

The approved source is copied into the immutable `data/raw/` location and is
validated before feature generation.

## 2024 census reference

`data/2024_census_bago_report (update).xlsx` is the Bago Region extract used
as the population base. `data/external/bago_census_2024.json` is the structured
copy the API serves. It keeps the published counts for:

- region, district, and township population by sex
- urban and rural residence where the workbook publishes it
- age groups for the region and each district
- household size and dwelling type as the living situation

Age groups are not published for individual townships. These counts are not
flood-model inputs.

## Interpretation limits

- A positive label means a flood day represented in available relief records.
  It is not a complete hydrological flood inventory.
- Rainfall is reanalysis data rather than a local rain-gauge measurement.
- River discharge is modeled GloFAS discharge, not measured gauge height.
- Copernicus GLO-30 elevation is a digital surface model on the EGM2008 geoid.
  It includes canopy and buildings, and it is not a flood-model input.
- Sparse relief impact fields must not be treated as complete observations.
- Synthetic data from older demo projects is not an approved real-data source.

All model and dashboard outputs must remain labeled as academic prototype
results unless independent validation establishes operational reliability.
