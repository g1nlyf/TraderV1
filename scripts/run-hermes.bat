@echo off
setlocal
set "ROOT=%~dp0.."
set "HERMES=%ROOT%\external\hermes-agent\.venv\Scripts\hermes.exe"
if not exist "%HERMES%" (
  echo [error] Hermes is not installed at external\hermes-agent\.venv.
  echo [hint] Clone https://github.com/nousresearch/hermes-agent and run: uv venv .venv --python 3.11 ^&^& uv pip install -e .
  exit /b 1
)

if exist "%USERPROFILE%\.hermes\.env" (
  for /f "usebackq tokens=1,* delims==" %%A in ("%USERPROFILE%\.hermes\.env") do (
    if /I "%%A"=="OPENROUTER_API_KEY" set "OPENROUTER_API_KEY=%%B"
  )
)
if not defined OPENROUTER_API_KEY if exist "%ROOT%\WalletScarper\.env" (
  for /f "usebackq tokens=1,* delims==" %%A in ("%ROOT%\WalletScarper\.env") do (
    if /I "%%A"=="OPENROUTER_API_KEY" set "OPENROUTER_API_KEY=%%B"
  )
)
if not defined OPENROUTER_API_KEY (
  echo [error] OPENROUTER_API_KEY is missing. Add it to WalletScarper\.env or %%USERPROFILE%%\.hermes\.env.
  exit /b 1
)

set "HERMES_INFERENCE_PROVIDER=openrouter"
if not defined HERMES_INFERENCE_MODEL set "HERMES_INFERENCE_MODEL=openai/gpt-oss-20b:free"
set "HERMES_ENABLE_PROJECT_PLUGINS=1"
if not defined HERMES_TOOLSETS set "HERMES_TOOLSETS=traderv1_operator"
cd /d "%ROOT%"

if "%~1"=="" (
  "%HERMES%" --provider openrouter -m "%HERMES_INFERENCE_MODEL%" --toolsets "%HERMES_TOOLSETS%"
) else (
  "%HERMES%" --toolsets "%HERMES_TOOLSETS%" %*
)
