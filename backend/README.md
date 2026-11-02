# Backend

FastAPI serves health, forecast, prediction, humanitarian planning, historical
weather, recorded flood history, elevation, alerts, and route-planning
endpoints.

The `baseline-logistic-v2` and `flood-help-v2` artifacts use twelve features
available for a future outlook: Open-Meteo rainfall, GloFAS discharge,
same-day/trailing hydrologic transforms, calendar seasonality, and coordinates.
NASA POWER remains a historical-weather display source and is not a live model
input.

Run from the project root with Python 3.12:

```powershell
uv venv --python 3.12 .venv
uv pip install --python .venv/Scripts/python.exe -r backend/requirements.txt -r ml/requirements.txt
Push-Location backend
../.venv/Scripts/python.exe -m pytest -q
../.venv/Scripts/python.exe -m uvicorn app.main:app --reload
Pop-Location
```

Inventory object detection needs the YOLO weights under `ml/runs/yolo` (or promoted
copies in `ml/models/object_detect`) plus the `ultralytics` and
`opencv-python-headless` packages from `backend/requirements.txt`. Restart the API
after installing or updating those dependencies.

The API is an academic prototype. It is not an operational warning, caseload,
dispatch, or public-safety service.
