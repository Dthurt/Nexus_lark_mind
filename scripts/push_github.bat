@echo off
chcp 65001 >nul
cd /d "E:\cursor\open_program\Nexus_lark_mind"

set "GIT=C:\Program Files\Git\cmd\git.exe"
if not exist "%GIT%" (
  echo Git not found at "%GIT%"
  echo Install Git for Windows first.
  pause
  exit /b 1
)

echo Using: %GIT%
"%GIT%" --version
echo.
"%GIT%" remote -v
echo.
echo Pushing to GitHub...
"%GIT%" push -u origin main
echo.
if errorlevel 1 (
  echo.
  echo Push failed. Common causes:
  echo  1. Cannot reach github.com - turn on VPN/proxy
  echo  2. Need login - a browser/credential window should appear
  echo.
)
pause
