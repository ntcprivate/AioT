@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo Run setup.bat first.
  pause
  exit /b 1
)
start "ECG Monitor" /b ".venv\Scripts\pythonw.exe" "%~dp0run.py"
