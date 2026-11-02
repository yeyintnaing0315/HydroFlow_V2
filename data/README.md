# Data directories

- `raw/` contains immutable, provenance-recorded input files.
- `processed/` contains reproducible generated outputs and is ignored by Git.
- `external/` holds independently sourced reference data.
  `external/bago_census_2024.json` is the 2024 census base for Bago Region:
  population by sex, urban and rural residence, age group, household size, and
  dwelling type. It is built from `2024_census_bago_report (update).xlsx`.

Long-range hydrology for prediction replay (optional local cache):

- Run `python scripts/download_bago_hydro_sources.py --start 1984-01-01` to fetch
  Open-Meteo ERA5 archive rainfall/met, NASA POWER daily met, and GloFAS discharge
  into `external/open_meteo_archive_daily/`, `external/nasa_power_hydro/`,
  `external/glofas_discharge/`, and merged `external/hydro_merged/` per township.
- The API timeline prefers these files when present (live APIs still fill recent forecast days).

Flood-model inputs stay in `raw/` and `processed/`. The census workbook
(`2024_census_bago_report (update).xlsx`) and relief list
(`ToPredit_Excel_Data.xlsx`) feed the allocation planner as baseline context
(census population/households and township relief totals), alongside live flood
and help model scores and warehouse stock.

Train humanitarian ML artifacts (from repo root):

```powershell
.venv/Scripts/python.exe ml/run.py process
.venv/Scripts/python.exe ml/run.py analyze-topredict
.venv/Scripts/python.exe ml/run.py train-help
.venv/Scripts/python.exe ml/run.py train-allocation
```

Restart the API after training so `/help` and `/allocation/plan` load
`artifacts/flood_help_pipeline.joblib` and `artifacts/allocation_pipeline.joblib`.
Optional demo warehouse stock: `python scripts/seed_demo_inventory.py` (also runs
on API startup when both depots are empty).
