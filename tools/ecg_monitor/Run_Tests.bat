@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run setup.bat first.
  pause
  exit /b 1
)
set QT_QPA_PLATFORM=offscreen
".venv\Scripts\python.exe" -m unittest discover -s tests -v
if errorlevel 1 goto error
".venv\Scripts\python.exe" benchmark_transport.py
if errorlevel 1 goto error
echo Host tests PASS. Hardware timing and simulator tests still require measurement.
pause
exit /b 0
:error
echo Host test failed. Inspect the error above; AI remains locked.
pause
exit /b 1
