# Run on the ASUS laptop (PowerShell):
#   cd D:\Ai_Project\HydroFlow_V2\scripts
#   powershell -ExecutionPolicy Bypass -File .\install_kitchenware_train_asus.ps1
#
# Creates train_kitchenware_terminal.py under the kitchenware dataset folder.

$ErrorActionPreference = "Stop"
$TargetDir = "C:\Users\ASUS\Downloads\kitchenware_yolo_dataset"
$RepoScript = Join-Path $PSScriptRoot "..\ml\detection\train_kitchenware_terminal.py"
$TargetFile = Join-Path $TargetDir "train_kitchenware_terminal.py"

if (-not (Test-Path $RepoScript)) {
    Write-Error "Missing source script: $RepoScript"
}

if (-not (Test-Path $TargetDir)) {
    Write-Host "Creating $TargetDir ..."
    New-Item -ItemType Directory -Force -Path $TargetDir | Out-Null
}

Copy-Item -Force $RepoScript $TargetFile
if (-not (Test-Path $TargetFile)) {
    Write-Error "Failed to create $TargetFile"
}

Write-Host "OK: $TargetFile"
Write-Host (Get-Item $TargetFile | Select-Object FullName, Length, LastWriteTime | Format-List | Out-String)
Write-Host @"

Next (in PowerShell):
  cd $TargetDir
  python -m venv .venv
  .\.venv\Scripts\Activate.ps1
  pip install ultralytics opencv-python-headless
  python train_kitchenware_terminal.py --weights yolov8m.pt --device 0 --batch 4 --epochs 100 --patience 20

"@
