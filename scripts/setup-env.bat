@echo off
setlocal
set "ROOT=%~dp0.."
set "APP=%ROOT%\WalletScarper"

if not exist "%APP%" (
  echo [error] WalletScarper app directory not found: %APP%
  exit /b 1
)

cd /d "%APP%"

if not exist ".env" (
  if exist ".env.example" (
    copy ".env.example" ".env" >nul
    echo [ok] Created WalletScarper\.env from .env.example. Add secrets locally if needed.
  ) else (
    echo [warn] .env.example is missing; create WalletScarper\.env manually.
  )
)

if not exist ".venv\Scripts\python.exe" (
  echo [info] Creating Python virtual environment in WalletScarper\.venv
  py -3.11 -m venv .venv
  if errorlevel 1 (
    echo [warn] py -3.11 failed; trying python -m venv.
    python -m venv .venv
  )
)

if not exist ".venv\Scripts\python.exe" (
  echo [error] Python virtual environment is missing. Install Python 3.11+ and rerun this script.
  exit /b 1
)

".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo [error] Dependency install failed.
  exit /b 1
)

echo [ok] Environment ready. No live trading path was enabled.
