@echo off
setlocal
set "ROOT=%~dp0.."
set "APP=%ROOT%\WalletScarper"
set "PY=%APP%\.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo [error] Missing virtualenv. Run scripts\setup-env.bat first.
  exit /b 1
)
if "%~1"=="" (
  echo [blocked] Provide a token mint. This script does not auto-select live market targets.
  echo Usage: scripts\run-calibration-window.bat TOKEN_MINT [POOL_ADDRESS] [SOURCE]
  echo SOURCE defaults to all_free. Allowed: dexscreener, geckoterminal, dexpaprika, all_free.
  exit /b 2
)
set "SOURCE=%~3"
if "%SOURCE%"=="" set "SOURCE=all_free"
cd /d "%APP%"
"%PY%" -m walletscarper stage2-calibration-window "%~1" "%~2" --source "%SOURCE%" --max-samples 3 --interval-seconds 30 --duration-seconds 300
