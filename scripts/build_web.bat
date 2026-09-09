@echo off
setlocal
cd /d "%~dp0.."

set "NODE_DIR=%CD%\.tools\node\node-v22.14.0-win-x64"
if exist "%NODE_DIR%\node.exe" (
  set "PATH=%NODE_DIR%;%PATH%"
)

where node >nul 2>nul
if errorlevel 1 (
  echo [build_web] Node.js not found. Install Node 20+ LTS or place portable Node under .tools\node\
  exit /b 1
)

cd web
if not exist node_modules (
  echo [build_web] npm install...
  call npm install
  if errorlevel 1 exit /b 1
)

echo [build_web] npm run build...
call npm run build
if errorlevel 1 exit /b 1

echo [build_web] Done. Output: web-static\
exit /b 0
