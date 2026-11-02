# HydroFlow V2 scaffold

This tree is a working copy of selected HydroFlow V1 source from `D:\Ai_Project\HydroFlow-V_1.2`. V1 was not edited.

## Copied

- `frontend/` source, Vite config, package files, Docker/nginx, and `frontend/.env.example`. Includes `App.tsx`, `styles.css`, `FloodPredictionDashboard.tsx`, `ResourceAllocationDashboard.tsx`, and `InventoryManagement.tsx`, plus their hooks, map components, and tests.
- `backend/` app, Alembic, tests, `Dockerfile`, `entrypoint.sh`, `requirements.txt`, `pytest.ini`, and `README.md`.
- `ml/hydroflow_ml`, `ml/tests`, root `ml/*.py` (including `run.py`), `ml/requirements.txt`, `ml/pytest.ini`, and `ml/README.md`.
- Promoted flood weights and metadata: `ml/models/bago_flood_model.joblib`, `bago_flood_model_metadata.json`, and the logistic joblib plus metadata (loaded by `prediction_secondary.py`).
- Promoted YOLO fallback weights: `ml/models/object_detect/{clothing,foods,kitchenware,utilities}/best.pt`.
- `data/external` (geography, `bago_census_2024.json`, `bago_river_points.csv`, and the hydro reference caches).
- Inventory SQL and README: `data/inventory/schema.sql`, `region_tables.sql`, `README.md`, and the small `data/inventory/docker-compose.yml`. `data/README.md` was kept with that folder.
- `docs/` (architecture, provenance, verification, and the diagram script).
- Root files: `docker-compose.yml`, `alembic.ini`, `run_server.py`, `.env.example`, `.dockerignore`, `.gitignore`, `.python-version`, and `README.md`.

## Created empty

- `ml/flood/` (`.gitkeep`)
- `ml/detection/` (`.gitkeep`)
- `data/cache/` (`.gitkeep`)

## Excluded

- `.venv`, `frontend/node_modules`, `frontend/dist`, `__pycache__`, `.pytest_cache`, `*.pyc`, `*.tsbuildinfo`
- `ml/runs/`
- Root `yolov8n.pt` and `yolov8s.pt`
- `hydroflow.db` (root and `backend/`)
- `.env` secrets (only `.env.example` files were copied; V1 had no real `.env`)
- `launch_backend.bat`, `backend_server.out`, `backend_server.err`
- Scratch files `backend/_check_hist.py`, `backend/_list_tables.py`, `backend/_tmp_outlook.py`, `_raw_sample.txt`, `_topredit_cols.txt`, `_topredit_sample.txt`, `_topredict_inspect.json`
- `desktop.ini`
- `data/inventory/pgdata`, `data/inventory/objectDetect`, and `data/Raw_Pic` (these paths were not present in V1)
- `frontend/src/prototype/` (entire directory)

Unused pages were left out after a search of `frontend/src` found no imports from `App.tsx`, the three dashboards, their hooks, or other source files:

- `frontend/src/DashboardHome.tsx`
- `frontend/src/HumanitarianDashboard.tsx`
- `frontend/src/MapsPage.tsx`
- `frontend/src/ReportsPage.tsx`
- `frontend/src/SettingsPage.tsx`

Not part of the selected copy, so left in V1:

- `scripts/` (`download_bago_hydro_sources.py`, `download_hydro_history.py`, `seed_demo_inventory.py`)
- Data-root workbooks (`ToPredit_Excel_Data.xlsx`, the translated copy, both census workbooks, and the year-range `.xlsx` files). `allocation_baseline.py` and `ml/hydroflow_ml/census.py` still point at those workbooks.
- `data/raw/`

## Missing expected files

- `data/processed/validated_daily.csv` is absent in V1 and was not copied. `data/processed/` does not exist in either tree.

## Check

Present: `backend/app/main.py`, `frontend/src/App.tsx`, `frontend/src/styles.css`, the three dashboards, `ml/models/bago_flood_model_metadata.json`, `docker-compose.yml`.

Absent: `.venv`, `frontend/node_modules`, `ml/runs`, `hydroflow.db`, and a real `.env`.
