@echo off
setlocal EnableExtensions
cd /d "%~dp0\.."

REM Thin wrapper → PowerShell implementation (status / -Open / -Install / …)
set "PS1=%~dp0start_local.ps1"
if not exist "%PS1%" (
  echo [ERROR] Missing %PS1%
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%" %*
exit /b %ERRORLEVEL%
