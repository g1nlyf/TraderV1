@echo off
setlocal
set "ROOT=%~dp0.."

echo [step] Checking environment
call "%~dp0setup-env.bat"
if errorlevel 1 exit /b 1

echo [step] Applying migrations
call "%~dp0run-migrations.bat"
if errorlevel 1 exit /b 1

echo [step] Running project health check
call "%~dp0run-health.bat"
if errorlevel 1 exit /b 1

if /I "%RUN_FIXTURE_ACCEPTANCE%"=="true" (
  echo [step] Running fixture acceptance because RUN_FIXTURE_ACCEPTANCE=true
  call "%~dp0run-final-acceptance.bat"
  if errorlevel 1 exit /b 1
) else (
  echo [skip] Fixture acceptance not run. Set RUN_FIXTURE_ACCEPTANCE=true to include it.
)

echo [step] Starting dashboard in a separate local window
start "TraderV1 Dashboard" /min cmd /c ""%~dp0run-dashboard.bat""
echo [ok] Dashboard URL: http://127.0.0.1:8787
echo [next] Open the dashboard, inspect Stage 2 and shadow gaps, then run scripts\run-calibration-smoke.bat.
echo [boundary] No live trading, signing, credential custody, route execution, or order-placement path was enabled.
