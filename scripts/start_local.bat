@echo off
setlocal EnableExtensions
cd /d "%~dp0\.."

set "ACTION=%~1"
if /I "%ACTION%"=="stop" goto :stop
if /I "%ACTION%"=="/stop" goto :stop
if /I "%ACTION%"=="--stop" goto :stop
if /I "%ACTION%"=="help" goto :help
if /I "%ACTION%"=="/?" goto :help
if /I "%ACTION%"=="-h" goto :help
if /I "%ACTION%"=="--help" goto :help
if not "%ACTION%"=="" if /I not "%ACTION%"=="start" (
  echo [ERROR] Unknown argument: %ACTION%
  echo Use: scripts\start_local.bat [start^|stop]
  exit /b 1
)

goto :start

:stop
echo === Nexus-Lark-Mind local stop ===
call :free_ports
echo Stopped.
exit /b 0

:help
echo Usage: scripts\start_local.bat [start^|stop]
echo   start  Start local services (default)
echo   stop   Stop services on ports 8000/8001/8002
exit /b 0

:start
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

REM Free ports if a previous instance is still running
echo Freeing ports 8000/8001/8002 if busy...
call :free_ports

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
echo Frontend:        Vue source in web\  (rebuild: scripts\build_web.bat)
echo Ctrl+C to stop, or: scripts\start_local.bat stop
echo.

python -m src.entry_local
endlocal
exit /b %ERRORLEVEL%

:free_ports
set "KILLED="
for %%P in (8000 8001 8002) do (
  for /f "tokens=5" %%A in ('netstat -ano ^| findstr ":%%P .*LISTENING"') do (
    echo   Killing PID %%A on port %%P
    taskkill /F /PID %%A >nul 2>&1
    set "KILLED=1"
  )
)
if not defined KILLED echo   Ports 8000/8001/8002 already free.
goto :eof
