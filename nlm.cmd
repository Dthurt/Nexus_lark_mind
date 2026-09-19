@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

REM Nexus Lark Mind — one-command local console
REM Usage: nlm ^| nlm start ^| nlm setup ^| nlm config ^| nlm crawl ^| nlm status ^| nlm stop ^| nlm repair

chcp 65001 >nul 2>&1
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

set "VENV_PY=%~dp0.venv\Scripts\python.exe"
set "BOOT=%~dp0scripts\nlm_boot.py"
set "PY="
set "NLM_NONINTERACTIVE="
set "NLM_SHOULD_PAUSE="

if not exist "%BOOT%" (
  echo [nlm] Missing scripts\nlm_boot.py
  call :maybe_pause
  exit /b 1
)

call :detect_flags %*

if exist "%VENV_PY%" (
  "%VENV_PY%" "%BOOT%" %*
  exit /b !ERRORLEVEL!
)

call :refresh_python_path
call :find_python
if defined PY goto :run_boot

REM Missing / stub / broken py: prompt or auto-hint (never silent-exit)
call :ensure_python_interactive
if defined PY goto :run_boot
call :maybe_pause
exit /b 1

:run_boot
if /I "!PY!"=="py" (
  py -3 "%BOOT%" %*
) else (
  "!PY!" "%BOOT%" %*
)
exit /b !ERRORLEVEL!

REM ---------------------------------------------------------------------------
:detect_flags
if defined CI set "NLM_NONINTERACTIVE=1"
if defined NLM_YES (
  if /I not "%NLM_YES%"=="0" if /I not "%NLM_YES%"=="false" if /I not "%NLM_YES%"=="no" set "NLM_NONINTERACTIVE=1"
)
echo %CMDCMDLINE% | find /I "/c" >nul
if not errorlevel 1 set "NLM_SHOULD_PAUSE=1"
:detect_flags_scan
if "%~1"=="" goto :eof
if /I "%~1"=="--yes" set "NLM_NONINTERACTIVE=1"
if /I "%~1"=="-y" set "NLM_NONINTERACTIVE=1"
shift
goto detect_flags_scan

:maybe_pause
if defined NLM_NONINTERACTIVE goto :eof
if not defined NLM_SHOULD_PAUSE goto :eof
echo.
echo Press any key to close / 按任意键关闭...
pause >nul
goto :eof

:refresh_python_path
set "PF86=%ProgramFiles(x86)%"
set "PATH=%LOCALAPPDATA%\Programs\Python\Python312;%LOCALAPPDATA%\Programs\Python\Python312\Scripts;%LOCALAPPDATA%\Programs\Python\Python311;%LOCALAPPDATA%\Programs\Python\Python311\Scripts;%LOCALAPPDATA%\Programs\Python\Python313;%LOCALAPPDATA%\Programs\Python\Python313\Scripts;%LOCALAPPDATA%\Programs\Python\Python310;%LOCALAPPDATA%\Programs\Python\Python310\Scripts;%LOCALAPPDATA%\Programs\Python\Launcher;%ProgramFiles%\Python312;%ProgramFiles%\Python311;%ProgramFiles%\Python313;%ProgramFiles%\Python310;%PF86%\Python312;%PF86%\Python311;%PF86%\Python313;%PF86%\Python310;%PATH%"
for /f "skip=2 tokens=1,2*" %%A in ('reg query "HKCU\Environment" /v Path 2^>nul') do (
  if /I "%%A"=="Path" set "PATH=%%C;!PATH!"
)
goto :eof

:find_python
set "PY="
call :try_py_exe "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if defined PY goto :eof
call :try_py_exe "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if defined PY goto :eof
call :try_py_exe "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
if defined PY goto :eof
call :try_py_exe "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
if defined PY goto :eof
call :try_py_exe "%ProgramFiles%\Python312\python.exe"
if defined PY goto :eof
call :try_py_exe "%ProgramFiles%\Python311\python.exe"
if defined PY goto :eof
call :try_py_exe "%ProgramFiles%\Python313\python.exe"
if defined PY goto :eof
call :try_py_exe "%ProgramFiles%\Python310\python.exe"
if defined PY goto :eof
call :try_py_exe "%ProgramFiles(x86)%\Python312\python.exe"
if defined PY goto :eof
call :try_py_exe "%ProgramFiles(x86)%\Python311\python.exe"
if defined PY goto :eof
call :try_py_exe "%ProgramFiles(x86)%\Python313\python.exe"
if defined PY goto :eof
call :try_py_exe "%ProgramFiles(x86)%\Python310\python.exe"
if defined PY goto :eof
for /f "delims=" %%I in ('where python3 2^>nul') do (
  call :try_py_exe "%%I"
  if defined PY goto :eof
)
for /f "delims=" %%I in ('where python 2^>nul') do (
  call :try_py_exe "%%I"
  if defined PY goto :eof
)
where py >nul 2>&1
if not errorlevel 1 (
  py -3 -c "import sys; raise SystemExit(0 if (3,10)<=sys.version_info<(3,14) else 1)" >nul 2>&1
  if not errorlevel 1 (
    set "PY=py"
    goto :eof
  )
)
goto :eof

:try_py_exe
set "_CAND=%~1"
if not defined _CAND goto :eof
if not exist "%_CAND%" goto :eof
echo %_CAND% | find /I "WindowsApps" >nul
if not errorlevel 1 goto :eof
"%_CAND%" -c "import sys; raise SystemExit(0 if (3,10)<=sys.version_info<(3,14) else 1)" >nul 2>&1
if errorlevel 1 goto :eof
set "PY=%_CAND%"
goto :eof

:ensure_python_interactive
if defined NLM_NONINTERACTIVE (
  echo.
  echo [nlm] 未找到可用的 Python 3.10-3.13。
  echo       Need Python 3.10-3.13. Microsoft Store stub is not a real interpreter.
  echo.
  echo Non-interactive / 非交互: install Python, then re-run nlm start
  echo.
  echo   winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
  echo.
  goto :eof
)

REM Same-console PowerShell UI + winget; path is written to NLM_PY_FILE (not stdout).
where powershell >nul 2>&1
if not errorlevel 1 (
  set "NLM_PY_FILE=%TEMP%\nlm_ensure_python_%RANDOM%.txt"
  if exist "%NLM_PY_FILE%" del /q "%NLM_PY_FILE%" >nul 2>&1
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0nlm.ps1" -EnsurePythonOnly
  if exist "%NLM_PY_FILE%" (
    set /p PY=<"%NLM_PY_FILE%"
    del /q "%NLM_PY_FILE%" >nul 2>&1
  )
  goto :eof
)

echo.
echo [nlm] 未找到可用的 Python 3.10-3.13。
echo       Need Python 3.10-3.13. Microsoft Store stub is not a real interpreter.
echo.
call :cmd_missing_menu
goto :eof

:cmd_missing_menu
echo [1] Auto-install Python 3.12 via winget  /  自动安装 Python 3.12（推荐）
echo [2] Open python.org download page         /  打开说明 / 下载页，我自己装
echo [3] Exit                                  /  退出
echo.
set "NLM_CHOICE="
set /p "NLM_CHOICE=Choose / 请选择 [1/2/3]: "
if not defined NLM_CHOICE goto :eof
if "!NLM_CHOICE!"=="1" (
  call :install_python_windows
  call :refresh_python_path
  call :find_python
  if defined PY (
    echo [nlm] Found Python: !PY!
    goto :eof
  )
  echo [nlm] Still no Python after install. Retry 1 or reopen this window.
  echo.
  goto cmd_missing_menu
)
if "!NLM_CHOICE!"=="2" (
  echo [nlm] Opening https://www.python.org/downloads/
  echo       Check "Add python.exe to PATH" when installing.
  start "" "https://www.python.org/downloads/"
  echo Install, then re-run nlm — or press 1 to retry.
  echo.
  goto cmd_missing_menu
)
if "!NLM_CHOICE!"=="3" (
  echo [nlm] Exit. Install Python 3.10-3.13, then run nlm again.
  goto :eof
)
echo [nlm] Please enter 1, 2, or 3
goto cmd_missing_menu

:install_python_windows
where winget >nul 2>&1
if errorlevel 1 (
  echo [nlm] winget not found. Opening python.org ...
  echo       Check "Add python.exe to PATH"
  start "" "https://www.python.org/downloads/"
  goto :eof
)
echo [nlm] winget install -e --id Python.Python.3.12 --scope user
winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
echo [nlm] winget exit !ERRORLEVEL! — rescan Python
call :refresh_python_path
call :find_python
if defined PY goto :eof
echo [nlm] Trying Python 3.11 ...
winget install -e --id Python.Python.3.11 --scope user --accept-package-agreements --accept-source-agreements
echo [nlm] winget exit !ERRORLEVEL! — rescan Python
goto :eof
