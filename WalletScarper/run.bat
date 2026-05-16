@echo off
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
if not exist ".venv\Scripts\python.exe" call install.bat
".venv\Scripts\python.exe" -m walletscarper run
