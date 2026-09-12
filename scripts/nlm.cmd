@echo off
REM Thin Windows shim: scripts\nlm.cmd web --open
setlocal
cd /d "%~dp0\.."
set "PY="
if exist "%LocalAppData%\Programs\Python\Python311\python.exe" set "PY=%LocalAppData%\Programs\Python\Python311\python.exe"
if not defined PY if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set "PY=%LocalAppData%\Programs\Python\Python312\python.exe"
if not defined PY if exist "%LocalAppData%\Programs\Python\Python313\python.exe" set "PY=%LocalAppData%\Programs\Python\Python313\python.exe"
if not defined PY set "PY=python"
"%PY%" -m src %*
exit /b %ERRORLEVEL%
