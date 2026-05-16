@echo off
setlocal
set "ROOT=%~dp0.."
set "APP=%ROOT%\WalletScarper"
set "PY=%APP%\.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo [error] Missing virtualenv. Run scripts\setup-env.bat first.
  exit /b 1
)
cd /d "%APP%"
"%PY%" -m walletscarper stage2-calibration-smoke --database-path tmp\calibration_smoke.sqlite3
