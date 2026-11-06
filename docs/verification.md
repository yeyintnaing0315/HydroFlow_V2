# Verification

Run commands from `D:\Ai_Project\HydroFlow_V2`.

## Pinned Python 3.12 environment

```powershell
uv venv --python 3.12 .venv
uv pip install --python .venv/Scripts/python.exe -r backend/requirements.txt -r ml/requirements.txt
```

The same environment must train and serve the saved scikit-learn artifacts.

## Machine learning

```powershell
.venv/Scripts/python.exe -m pytest -c ml/pytest.ini ml/tests
.venv/Scripts/python.exe ml/run.py run-all
```

## Backend

```powershell
Push-Location backend
../.venv/Scripts/python.exe -m pytest -q
../.venv/Scripts/python.exe -m uvicorn app.main:app --reload
Pop-Location
```

Open `http://127.0.0.1:8000/health` and `/docs`.

## Frontend

```powershell
Push-Location frontend
npm ci
npm test
npm run build
npm run dev
Pop-Location
```

Open `http://127.0.0.1:5173`.

To serve the built UI and the API together on that same address, build the
frontend, then from the repository root run `python run_server.py`. Use either
the Vite dev server or `run_server.py`, since both bind port 5173.

## Integrated Docker stack

On the new laptop the project folder is `D:\HydroFlow`. Start Docker Desktop first, then:

```powershell
powershell -ExecutionPolicy Bypass -File D:\HydroFlow\scripts\run-docker.ps1
```

Open `http://127.0.0.1:8080`. Stop with Ctrl+C, then `docker compose down` from that same folder.
The first build downloads PyTorch and can take several minutes. Docker Desktop must report a healthy Linux engine before running this command.
