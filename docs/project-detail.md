# HydroFlow V2 — Project detail

## Purpose

HydroFlow V2 is an academic flood-outlook and humanitarian-planning prototype for Bago Region, Myanmar. It connects a leakage-aware machine-learning pipeline, a FastAPI service, and a React map dashboard so a user can inspect rainfall, modeled river discharge, a flood-occurrence score, an assistance-demand illustration, recorded flood history, 2024 census context, terrain elevation, and a sample delivery route.

The system demonstrates a correct end-to-end workflow. It is not validated for operational emergency decisions, public warnings, caseload estimates, or dispatch.

## Study area and question

The study area is Bago Region. The unit of analysis is a township-day.

The flood model asks whether a township-day matches the source dataset’s relief-derived flood indicator. That indicator is incomplete: a positive label means a flood day present in the available relief records, not a complete hydrological inventory.

A second model asks whether recorded households or affected people are greater than zero, then estimates expected people and households for a short planning illustration. Impact counts are targets, not inputs.

## What the system does

1. Validates the immutable Bago daily table and rebuilds features without future leakage.
2. Trains two forecast-valid models and saves scikit-learn pipelines with metadata.
3. Serves inference only. The API does not retrain on request.
4. Pulls live outlook inputs from Open-Meteo rainfall and GloFAS modeled discharge.
5. Shows historical NASA POWER weather, Copernicus elevation, recorded floods, and the 2024 Bago census as context. Those sources are not live model features.
6. Scores an academic risk level and, for high or severe days, stores an in-app prototype alert.
7. Orders a caller-supplied delivery round through Kardinal. The dashboard sends township centroids, so the route is an illustration, not a site-level plan.

## Architecture

| Part | Role |
| --- | --- |
| `data/` | Immutable source data, validated daily table, and the structured 2024 census extract |
| `ml/` | Ingestion, leakage checks, training, and evaluation |
| `artifacts/` | Saved pipelines and metadata. The API loads these once. |
| `backend/` | FastAPI inference, external clients, and persistence |
| `frontend/` | React/TypeScript dashboard with Leaflet |
| `docker-compose.yml` | PostgreSQL 16, FastAPI, and the frontend on port 8080 |

Local development can use SQLite. The Docker stack uses PostgreSQL for locations, observation metadata, and alerts. Source CSVs and model artifacts stay on the filesystem.

Data flow:

1. The validated Bago CSV is transformed by `ml/hydroflow_ml/`.
2. Training writes `baseline-logistic-v2` and `flood-help-v2`.
3. FastAPI builds the twelve live features for a selected township and date, then runs the saved pipelines.
4. Risk scoring is a separate documented heuristic, not a third learned model.
5. The dashboard renders only backend responses and labels demo inputs.

## Models

Both models use twelve features that exist for a future outlook: Open-Meteo rainfall, GloFAS discharge, same-day and trailing hydrologic transforms, calendar seasonality, and coordinates. NASA POWER soil wetness and humidity were removed because those retrospective fields are not reliably available on outlook dates.

Preprocessing and the classifier are fit on the training block only. Numeric fields are median-imputed and standardized. The decision threshold maximizes flood-class or help-class F1 on the validation block. The final chronological test block is untouched until evaluation.

**Flood occurrence (`baseline-logistic-v2`).** Class-weighted logistic regression. The label is the same calendar day as rainfall and discharge, so same-day weather is contemporaneous with the label, not a forecast lead.

**Flood help (`flood-help-v2`).** A classifier marks `help_needed` when recorded households or affected people are greater than zero. Two Ridge models then estimate `log1p(affected_people)` and `log1p(households)`, fit only on training rows where help was needed. Expected counts are help probability times the magnitude estimate. Shelter kits, 3-day food rations, and drinking water multiply those counts by fixed planning ratios. Assistance priority applies a retrospective severity rule to the expected counts.

**Severity rule.** `academic_impact_severity` is not learned. Score = households + affected people / 5. Bands are none (0), low (>0), moderate (≥100), high (≥500), and severe (≥2,000). It uses information available after an event and must not be described as forecast severity.

### Reported results

Untouched chronological test, flood occurrence:

| Model | Precision | Recall | F1 | PR-AUC |
| --- | ---: | ---: | ---: | ---: |
| V1, 14 features including NASA POWER | 0.0612 | 0.2727 | 0.1000 | 0.1885 |
| V2, 12 forecast-available features | 0.0155 | 0.2727 | 0.0293 | 0.0238 |

Untouched chronological test, flood-help classification:

| Model | Precision | Recall | F1 | Expected-people MAE |
| --- | ---: | ---: | ---: | ---: |
| V1 | 0.0408 | 0.2000 | 0.0678 | 353.2 |
| V2 | 0.0103 | 0.2000 | 0.0196 | 399.2 |

V2 is the served model because its inputs can be obtained for a future date. The lower scores are reported on purpose. The repair improves serving validity; it does not claim better predictive skill.

The source table has 40,172 township-days and 220 positive flood rows (0.55%). Chronological blocks contain 42 train, 167 validation, and 11 test flood rows. Labels are concentrated in 2024 (167), with 11 in 2025 and none in the available 2026 rows. No township has five test positives, so township test metrics are suppressed.

## External data

| Source | Use |
| --- | --- |
| Bago relief workbooks | Flood-day labels and impact counts |
| Open-Meteo | Historical reanalysis rainfall and forecast rainfall |
| GloFAS via Open-Meteo Flood API | Modeled discharge, not measured river height |
| NASA POWER | Retrospective weather charts only |
| OpenTopography Copernicus GLO-30 | Display elevation on EGM2008; includes canopy and buildings |
| 2024 Myanmar census, Bago extract | Population, age groups, household size, and dwelling type |
| Open Admin Data | Bago district and township centroids |
| Kardinal | Delivery-stop ordering; API key stays on the server |

API keys live in `.env` and are not written into source, logs, or responses.

## Dashboard

The research view shows Bago districts and townships on a Leaflet map, a forecast outlook, historical weather, recorded flood history, elevation, in-app alerts, and a route planner (car, truck, or fly; optional return to origin).

The humanitarian view reads `/help` and `/census`. It shows expected people and households, a 3-day planning package, assistance priority, and census population, age, and dwelling context for the selected place. Age groups are published for the region and districts, not for individual townships. Census figures are reference context, not model features.

## API surface

- Prediction: `POST /predict`, `POST /outlook`, `GET /risk`
- Humanitarian: `POST /help`, `GET /help-brief`, `GET /census`
- Context: `GET /forecast`, `GET /historical`, `GET /flood-history`, `GET /topography`, `GET /bago-areas`, `GET /townships`
- Operations: `GET /health`, `GET /alerts`, `POST /routes`

High and severe outlook days can write a prototype alert. The stored message states that the result uses Open-Meteo and GloFAS and is not an operational warning.

## Limits

- Test flood F1 is about 0.029 because positives are rare and shift over time.
- Scores are not independently calibrated operational probabilities.
- GloFAS discharge is not measured river height.
- Severity bands are retrospective impact rules.
- Alerts are in-app prototype records, not official notifications.
- Help counts and planning ratios are academic illustrations.
- No output is suitable for public-safety use without independent hydrological validation and local authority review.

The next data step is independently verified flood labels for later years, with event dates and township provenance kept. A new untouched time block should be used only after that coverage is confirmed.

## How to run

From the project root, with Python 3.12:

```powershell
uv venv --python 3.12 .venv
uv pip install --python .venv/Scripts/python.exe -r backend/requirements.txt -r ml/requirements.txt
.venv/Scripts/python.exe ml/run.py run-all
docker compose up --build
```

Open `http://127.0.0.1:8080`.

Exact test commands are in `docs/verification.md`. Model comparison and the label audit are in `docs/model-repair-report.md`.
