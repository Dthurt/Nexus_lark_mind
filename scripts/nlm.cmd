@echo off
REM Thin Windows shim: scripts\nlm.cmd web --open
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0\.."
set "PY="

if exist "%CD%\.venv\Scripts\python.exe" (
  call :try_py "%CD%\.venv\Scripts\python.exe"
)

if not defined PY call :try_py "%LocalAppData%\Programs\Python\Python312\python.exe"
if not defined PY call :try_py "%LocalAppData%\Programs\Python\Python311\python.exe"
if not defined PY call :try_py "%LocalAppData%\Programs\Python\Python313\python.exe"
if not defined PY call :try_py "%LocalAppData%\Programs\Python\Python310\python.exe"
if not defined PY call :try_py "%ProgramFiles%\Python312\python.exe"
if not defined PY call :try_py "%ProgramFiles%\Python311\python.exe"
if not defined PY call :try_py "%ProgramFiles%\Python313\python.exe"
if not defined PY call :try_py "%ProgramFiles%\Python310\python.exe"
if not defined PY call :try_py "%ProgramFiles(x86)%\Python312\python.exe"
if not defined PY call :try_py "%ProgramFiles(x86)%\Python311\python.exe"
if not defined PY call :try_py "%ProgramFiles(x86)%\Python313\python.exe"
if not defined PY call :try_py "%ProgramFiles(x86)%\Python310\python.exe"

if not defined PY (
  for /f "delims=" %%I in ('where python3 2^>nul') do (
    if not defined PY call :try_py "%%I"
  )
)
if not defined PY (
  for /f "delims=" %%I in ('where python 2^>nul') do (
    if not defined PY call :try_py "%%I"
  )
)

if not defined PY (
  echo [nlm] Python 3.10-3.13 not found (Store stub skipped).
  if exist "%CD%\nlm.cmd" (
    echo [nlm] Handing off to nlm.cmd for install prompt...
    call "%CD%\nlm.cmd" %*
    exit /b !ERRORLEVEL!
  )
  echo [nlm] Run nlm.cmd from the repo root to auto-install.
  exit /b 1
)

"%PY%" -m src %*
exit /b %ERRORLEVEL%

:try_py
set "_CAND=%~1"
if not defined _CAND goto :eof
if not exist "%_CAND%" goto :eof
echo %_CAND% | find /I "WindowsApps" >nul
if not errorlevel 1 goto :eof
"%_CAND%" -c "import sys; raise SystemExit(0 if (3,10)<=sys.version_info<(3,14) else 1)" >nul 2>&1
if errorlevel 1 goto :eof
set "PY=%_CAND%"
goto :eof
