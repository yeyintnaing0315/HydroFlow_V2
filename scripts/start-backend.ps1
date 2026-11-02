# Start the API with the project venv (includes YOLO / OpenCV for inventory detect).
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
  Write-Error "Missing .venv. From repo root run: uv venv --python 3.12 .venv; uv pip install -r backend/requirements.txt -r ml/requirements.txt"
  exit 1
}
Push-Location (Join-Path $Root "backend")
& $Python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
Pop-Location
