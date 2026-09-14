@echo off
setlocal EnableExtensions
cd /d "%~dp0\.."

set "PS1=%~dp0dev.ps1"
if not exist "%PS1%" (
  echo [ERROR] Missing %PS1%
  exit /b 1
)

echo === Local DEBUG (backend + Vite HMR) ===
echo Open http://127.0.0.1:5173 for UI hot reload
echo API remains on http://127.0.0.1:8000
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%" %*
exit /b %ERRORLEVEL%
