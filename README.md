# HydroFlow V2

HydroFlow V2 is an academic flood-prediction and early-warning prototype for
Bago Region, Myanmar. This tree is the V2 working copy.

The project is not validated for operational emergency decisions.

## Components

- `backend/` — FastAPI application and tests
- `ml/` — reproducible data, feature, training, and evaluation code
- `data/` — immutable source data and generated processed data
- `docs/` — architecture, provenance, verification, and academic limitations
- `frontend/` — React/TypeScript dashboard
- `docker-compose.yml` — PostgreSQL, FastAPI, and frontend deployment

## Data policy

Existing Bago relief labels and climate records will be reused from the earlier
`Hydroflow` project only after provenance and validation checks. Modeled river
discharge must not be described as measured river water level.

## Current working scope

- Validated Bago ingestion and leakage-aware feature pipeline
- Chronological Logistic Regression flood-occurrence baseline
- Flood-help model for humanitarian assistance demand (expected people, households, and a 3-day planning package)
- FastAPI health, prediction, risk, forecast, alerts, weather history, and recorded flood history
- Open-Meteo rainfall and GloFAS discharge for model outlooks
- NASA POWER historical weather, OpenTopography elevation, and Kardinal route clients
- React/TypeScript dashboard with Leaflet
- SQLite local persistence and PostgreSQL Docker deployment

See `docs/verification.md` for exact test and run commands. The simplest
integrated start is:

```powershell
uv venv --python 3.12 .venv
uv pip install --python .venv/Scripts/python.exe -r backend/requirements.txt -r ml/requirements.txt
.venv/Scripts/python.exe ml/run.py run-all
docker compose up --build
```

Then open `http://127.0.0.1:8080`.

The forecast-valid V2 model deliberately excludes NASA POWER fields that are
unavailable for future dates. Its untouched-test flood F1 is approximately
0.029, and the flood-help model's untouched-test F1 is approximately 0.020.
These weak results are reported deliberately: the prototype demonstrates a
correct end-to-end workflow, not a reliable emergency or relief model. See
`docs/model-repair-report.md` for the V1/V2 comparison and label audit.
