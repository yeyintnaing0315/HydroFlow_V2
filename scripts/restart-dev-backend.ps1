# Stop duplicate uvicorn workers on 8000, then start one HydroFlow backend from this repo.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$backend = Join-Path $root "backend"
$python = Join-Path $root ".venv\Scripts\python.exe"

Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -match "uvicorn.*--port\s+8000" } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

Start-Sleep -Seconds 2
$env:PYTHONPATH = $backend
Set-Location $backend
& $python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
