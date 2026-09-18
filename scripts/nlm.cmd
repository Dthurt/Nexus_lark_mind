@echo off
REM Thin Windows shim: scripts\nlm.cmd web --open
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0\.."
set "PY="

if exist "%CD%\.venv\Scripts\python.exe" (
  "%CD%\.venv\Scripts\python.exe" -c "import sys; raise SystemExit(0 if (3,11)<=sys.version_info<(3,14) else 1)" >nul 2>&1
  if not errorlevel 1 set "PY=%CD%\.venv\Scripts\python.exe"
)

if not defined PY if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set "PY=%LocalAppData%\Programs\Python\Python312\python.exe"
if not defined PY if exist "%LocalAppData%\Programs\Python\Python311\python.exe" set "PY=%LocalAppData%\Programs\Python\Python311\python.exe"
if not defined PY if exist "%LocalAppData%\Programs\Python\Python313\python.exe" set "PY=%LocalAppData%\Programs\Python\Python313\python.exe"

if not defined PY (
  for /f "delims=" %%I in ('where python3 2^>nul') do (
    echo %%I | find /I "WindowsApps" >nul
    if errorlevel 1 (
      if not defined PY set "PY=%%I"
    )
  )
)
if not defined PY (
  for /f "delims=" %%I in ('where python 2^>nul') do (
    echo %%I | find /I "WindowsApps" >nul
    if errorlevel 1 (
      if not defined PY set "PY=%%I"
    )
  )
)

if not defined PY (
  echo [nlm] Python 3.11-3.13 not found (Store stub skipped).
  if exist "%CD%\nlm.cmd" (
    echo [nlm] Handing off to nlm.cmd for install prompt...
    call "%CD%\nlm.cmd" %*
    exit /b !ERRORLEVEL!
  )
  exit /b 1
)

"%PY%" -m src %*
exit /b %ERRORLEVEL%
