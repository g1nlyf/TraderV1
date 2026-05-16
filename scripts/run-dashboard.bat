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
echo [info] Starting local read-only dashboard at http://127.0.0.1:8787
"%PY%" -m walletscarper web
