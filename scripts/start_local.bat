@echo off
setlocal EnableExtensions
cd /d "%~dp0\.."

REM Thin wrapper -> PowerShell implementation (status / -Open / -Install / ...)
REM Double-click must not flash-exit if Python is missing or start_local.ps1 fails.

set "NLM_SHOULD_PAUSE="
if defined CI goto :run
if defined NLM_YES if /I not "%NLM_YES%"=="0" if /I not "%NLM_YES%"=="false" if /I not "%NLM_YES%"=="no" goto :run
echo %CMDCMDLINE% | find /I "/c" >nul
if not errorlevel 1 set "NLM_SHOULD_PAUSE=1"

:run
set "PS1=%~dp0start_local.ps1"
if not exist "%PS1%" (
  echo [ERROR] Missing %PS1%
  call :maybe_pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%" %*
set "EC=%ERRORLEVEL%"
if not "%EC%"=="0" call :maybe_pause
exit /b %EC%

:maybe_pause
if defined CI goto :eof
if not defined NLM_SHOULD_PAUSE goto :eof
echo.
echo Press any key to close...
pause >nul
goto :eof
