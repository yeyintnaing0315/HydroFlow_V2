# Flood offline data (2010–present)

## One-time setup

```powershell
# From repo root, with .venv active:
.venv\Scripts\python.exe -m app.services.hydro_download --start 2010-01-01
.venv\Scripts\python.exe ml\flood\collect_offline.py
.venv\Scripts\python.exe ml\flood\ingest_rasters.py
```

Optional slow/network steps:

```powershell
.venv\Scripts\python.exe ml\flood\collect_offline.py --chirps --cems
```

Requires `.env` keys: `CDSAPI_KEY`, `COPERNICUS_GFM_TOKEN` (GFM validation only).

Place Bago clips under `data/external/rasters/` (`jrc_flood/`, `hand/`, `worldcover/`, `hydrobasins/`) before re-running `ingest_rasters.py` for real zonal stats.

## Retrain served model

```powershell
.venv\Scripts\python.exe ml\retrain_served_model.py
.venv\Scripts\python.exe ml\flood\compare_logistic.py
```
