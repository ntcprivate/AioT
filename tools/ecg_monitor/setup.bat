@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  py -3.13 -m venv .venv
  if errorlevel 1 goto error
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto error
".venv\Scripts\python.exe" -c "import PySide6,pyqtgraph,serial,numpy,scipy; print('ECG Monitor installation OK')"
if errorlevel 1 goto error
echo Setup complete. Double-click Start_ECG_Monitor.bat
pause
exit /b 0
:error
echo Setup failed. Install Python 3.13 with Python Launcher, check Internet, and retry.
echo This script does not modify the project-root .venv.
pause
exit /b 1
