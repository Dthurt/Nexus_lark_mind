@echo off
setlocal EnableExtensions
cd /d "%~dp0"

REM Nexus Lark Mind — one-command local console
REM Usage: nlm ^| nlm start ^| nlm setup ^| nlm config ^| nlm crawl ^| nlm status ^| nlm stop ^| nlm repair

chcp 65001 >nul 2>&1
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

set "VENV_PY=%~dp0.venv\Scripts\python.exe"
set "BOOT=%~dp0scripts\nlm_boot.py"

if not exist "%BOOT%" (
  echo [nlm] Missing scripts\nlm_boot.py
  exit /b 1
)

if exist "%VENV_PY%" (
  "%VENV_PY%" "%BOOT%" %*
  exit /b %ERRORLEVEL%
)

REM First run: use system Python to bootstrap
where py >nul 2>&1
if %ERRORLEVEL%==0 (
  py -3 "%BOOT%" %*
  exit /b %ERRORLEVEL%
)

where python >nul 2>&1
if %ERRORLEVEL%==0 (
  python "%BOOT%" %*
  exit /b %ERRORLEVEL%
)

echo [nlm] Python 3.11+ not found. Install from https://www.python.org/downloads/
echo       Tip: check "Add python.exe to PATH"
exit /b 1
