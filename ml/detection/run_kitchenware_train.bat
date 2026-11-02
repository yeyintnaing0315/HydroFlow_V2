@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\activate.bat" (
  python -m venv .venv
)
call .venv\Scripts\activate.bat
pip install ultralytics opencv-python-headless -q
python "%~dp0train_kitchenware_terminal.py" %*
pause
