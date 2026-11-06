# Start HydroFlow in Docker.
# On the new laptop the project folder is D:\HydroFlow.
# Docker Desktop must already be running.
#
#   powershell -ExecutionPolicy Bypass -File D:\HydroFlow\scripts\run-docker.ps1

$ErrorActionPreference = "Stop"

function Find-ProjectRoot {
    $candidates = @(
        "D:\HydroFlow",
        (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
    )
    foreach ($candidate in $candidates) {
        if (Test-Path (Join-Path $candidate "docker-compose.yml")) {
            return (Resolve-Path $candidate).Path
        }
        if (-not (Test-Path $candidate)) {
            continue
        }
        $nested = Get-ChildItem -Path $candidate -Directory -ErrorAction SilentlyContinue |
            Where-Object { Test-Path (Join-Path $_.FullName "docker-compose.yml") } |
            Select-Object -First 1
        if ($nested) {
            return $nested.FullName
        }
    }
    return $null
}

$Root = Find-ProjectRoot
if (-not $Root) {
    Write-Error "Could not find docker-compose.yml in D:\HydroFlow. Unzip or clone the GitHub project there first."
}

Set-Location $Root
Write-Host "Project folder: $Root"

docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Error "Docker Desktop is not running. Open Docker Desktop, wait until it is ready, then run this script again."
}

Write-Host "Building and starting HydroFlow. The first build downloads PyTorch and can take several minutes."
docker compose up --build
