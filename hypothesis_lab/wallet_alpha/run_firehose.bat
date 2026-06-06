@echo off
REM Durable free firehose collector (GeckoTerminal, no key, paper-research only).
REM Usage:  run_firehose.bat            -> loop every 15 min (default)
REM         run_firehose.bat once       -> single tick
REM         run_firehose.bat dry        -> dry-run (no writes)
cd /d "%~dp0\..\.."
if "%~1"=="once" (
  py hypothesis_lab\wallet_alpha\firehose_collector.py --once --max-pools 40 --pages 2
) else if "%~1"=="dry" (
  py hypothesis_lab\wallet_alpha\firehose_collector.py --dry-run --max-pools 5 --pages 1
) else (
  py hypothesis_lab\wallet_alpha\firehose_collector.py --loop --interval 900 --max-pools 40 --pages 2
)
