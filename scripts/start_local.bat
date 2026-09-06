@echo off
setlocal EnableExtensions
cd /d "%~dp0\.."

echo === Nexus-Lark-Mind local start ===

REM Prefer real Python installs over Windows Store stub
set "PY="
if exist "%LocalAppData%\Programs\Python\Python311\python.exe" set "PY=%LocalAppData%\Programs\Python\Python311\python.exe"
if not defined PY if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set "PY=%LocalAppData%\Programs\Python\Python312\python.exe"
if not defined PY if exist "%LocalAppData%\Programs\Python\Python313\python.exe" set "PY=%LocalAppData%\Programs\Python\Python313\python.exe"
if not defined PY where python >nul 2>&1 && for /f "delims=" %%i in ('where python') do (
  echo %%i | findstr /i "WindowsApps" >nul || if not defined PY set "PY=%%i"
)
if not defined PY (
  echo [ERROR] Python 3.11+ not found. Install from https://www.python.org/downloads/
  echo Make sure "Add python.exe to PATH" is checked.
  exit /b 1
)

echo Using: %PY%
"%PY%" --version

if not exist .venv (
  echo Creating venv...
  "%PY%" -m venv .venv
)

call .venv\Scripts\activate.bat
python -m pip install -q --upgrade pip
python -m pip install -q -r requirements.txt

if not exist .env copy /Y .env.example .env >nul
if not exist data mkdir data
if not exist logs mkdir logs

REM Force local overrides for this session (do not rewrite secrets in .env)
set KERNEL_RPC_URL=http://127.0.0.1:8001
set ORCHESTRATOR_RPC_URL=http://127.0.0.1:8002
set REDIS_URL=memory://local
set PLUGINS_DIR=plugins_volume
set WEB_STATIC_DIR=web-static
set DATABASE_URL=sqlite+aiosqlite:///data/nexus.db
set PYTHONPATH=%CD%

echo.
echo Web UI:          http://127.0.0.1:8000
echo Kernel health:   http://127.0.0.1:8001/health
echo Orchestrator:    http://127.0.0.1:8002/health
echo Broker:          memory://local  (no Redis needed)
echo Ctrl+C to stop
echo.

python -m src.entry_local
endlocal
