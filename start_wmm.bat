@echo off
rem Windows Maintenance Manager launcher.
rem Installs or updates the protected copy in Program Files, runs the health check and starts the console.
setlocal
cd /d "%~dp0"
title Windows Maintenance Manager

where python >nul 2>&1
if errorlevel 1 (
  echo Python was not found. Install Python 3.9 or newer for all users from https://www.python.org/downloads/
  echo and tick "Add python.exe to PATH".
  pause
  exit /b 1
)
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)"
if errorlevel 1 (
  echo Python 3.9 or newer is required. Found:
  python --version
  pause
  exit /b 1
)

python wmm.py --auto-install %*
if errorlevel 1 pause
