# Nexus Lark Mind — one-command local console
# Usage: .\nlm.ps1 | .\nlm.ps1 start | setup | config | crawl | status | stop | repair
# Encoding: UTF-8 (BOM written on save). Chinese UI for missing Python.

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

try {
  [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
  $OutputEncoding = [System.Text.Encoding]::UTF8
  chcp 65001 | Out-Null
} catch { }

$Boot = Join-Path $Root "scripts\nlm_boot.py"
$VenvPy = Join-Path $Root ".venv\Scripts\python.exe"

$EnsurePythonOnly = $false
$NlmArgs = @($args)
if ($NlmArgs.Count -gt 0 -and @("-EnsurePythonOnly", "-ensurePythonOnly") -contains $NlmArgs[0]) {
  $EnsurePythonOnly = $true
  if ($NlmArgs.Count -gt 1) { $NlmArgs = $NlmArgs[1..($NlmArgs.Count - 1)] } else { $NlmArgs = @() }
}

function Test-NlmNonInteractive {
  if ($env:CI) { return $true }
  if ($env:NLM_YES -match '^(1|true|yes|y)$') { return $true }
  foreach ($a in $NlmArgs) {
    if ($a -eq "--yes" -or $a -eq "-y") { return $true }
  }
  try {
    if ([Console]::IsInputRedirected) { return $true }
  } catch { }
  try {
    if (-not [Environment]::UserInteractive) { return $true }
  } catch { }
  return $false
}

function Test-NlmShouldPause {
  if (Test-NlmNonInteractive) { return $false }
  if ($EnsurePythonOnly) { return $false }
  if ($env:NLM_SHOULD_PAUSE -eq "1") { return $true }
  try {
    if ([Console]::IsInputRedirected) { return $false }
  } catch { }
  # Explorer "Run with PowerShell" / double-click: no leftover args, console will close.
  if ($NlmArgs.Count -eq 0 -and $Host.Name -eq "ConsoleHost") {
    return $true
  }
  return $false
}

function Wait-NlmIfClosing {
  if (-not (Test-NlmShouldPause)) { return }
  try {
    Write-Host ""
    Write-Host "Press Enter to close / 按 Enter 关闭..."
    [void](Read-Host)
  } catch { }
}

function Update-NlmProcessPath {
  $known = @(
    "$env:LOCALAPPDATA\Programs\Python\Python312",
    "$env:LOCALAPPDATA\Programs\Python\Python312\Scripts",
    "$env:LOCALAPPDATA\Programs\Python\Python311",
    "$env:LOCALAPPDATA\Programs\Python\Python311\Scripts",
    "$env:LOCALAPPDATA\Programs\Python\Python313",
    "$env:LOCALAPPDATA\Programs\Python\Python313\Scripts",
    "$env:LOCALAPPDATA\Programs\Python\Python310",
    "$env:LOCALAPPDATA\Programs\Python\Python310\Scripts",
    "$env:LOCALAPPDATA\Programs\Python\Launcher",
    "$env:ProgramFiles\Python312",
    "$env:ProgramFiles\Python311",
    "$env:ProgramFiles\Python313",
    "$env:ProgramFiles\Python310",
    "${env:ProgramFiles(x86)}\Python312",
    "${env:ProgramFiles(x86)}\Python311",
    "${env:ProgramFiles(x86)}\Python313",
    "${env:ProgramFiles(x86)}\Python310"
  )
  $machine = ""
  $user = ""
  try { $machine = [Environment]::GetEnvironmentVariable("Path", "Machine") } catch { }
  try { $user = [Environment]::GetEnvironmentVariable("Path", "User") } catch { }
  $env:Path = (($known + @($user, $machine, $env:Path)) | Where-Object { $_ }) -join ";"
}

function Test-NlmPythonExe {
  param([string]$Exe)
  if (-not $Exe) { return $false }
  if ($Exe -match "WindowsApps") { return $false }
  if ($Exe -ne "py" -and -not (Test-Path -LiteralPath $Exe)) { return $false }
  $code = "import sys; raise SystemExit(0 if (3,10)<=sys.version_info<(3,14) else 1)"
  try {
    if ($Exe -eq "py") {
      & py -3 -c $code 2>$null | Out-Null
    } else {
      & $Exe -c $code 2>$null | Out-Null
    }
    return ($LASTEXITCODE -eq 0)
  } catch {
    return $false
  }
}

function Find-NlmPython {
  if (Test-Path -LiteralPath $VenvPy) {
    if (Test-NlmPythonExe $VenvPy) { return $VenvPy }
  }
  $candidates = @(
    "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python310\python.exe",
    "$env:ProgramFiles\Python312\python.exe",
    "$env:ProgramFiles\Python311\python.exe",
    "$env:ProgramFiles\Python313\python.exe",
    "$env:ProgramFiles\Python310\python.exe",
    "${env:ProgramFiles(x86)}\Python312\python.exe",
    "${env:ProgramFiles(x86)}\Python311\python.exe",
    "${env:ProgramFiles(x86)}\Python313\python.exe",
    "${env:ProgramFiles(x86)}\Python310\python.exe"
  )
  foreach ($c in $candidates) {
    if ($c -and (Test-NlmPythonExe $c)) { return $c }
  }
  foreach ($name in @("python3", "python")) {
    $cmds = @(Get-Command $name -All -ErrorAction SilentlyContinue)
    foreach ($cmd in $cmds) {
      if ($cmd.Source -and $cmd.Source -notmatch "WindowsApps" -and (Test-NlmPythonExe $cmd.Source)) {
        return $cmd.Source
      }
    }
  }
  $py = Get-Command py -ErrorAction SilentlyContinue
  if ($py -and $py.Source -notmatch "WindowsApps" -and (Test-NlmPythonExe "py")) {
    return "py"
  }
  return $null
}

function Write-NlmMissingPython {
  Write-Host ""
  Write-Host "[nlm] 未找到可用的 Python 3.10-3.13。" -ForegroundColor Red
  Write-Host "      Need Python 3.10-3.13 (Microsoft Store stub is not a real interpreter)." -ForegroundColor Red
  Write-Host ""
}

function Write-NlmInstallHint {
  Write-Host "Windows 安装命令 / install command:"
  Write-Host "  winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements"
  Write-Host "然后重新打开终端，再运行 nlm start"
}

function Install-NlmPython {
  $tried = @()
  Update-NlmProcessPath
  $winget = Get-Command winget -ErrorAction SilentlyContinue
  if ($winget) {
    foreach ($pkg in @("Python.Python.3.12", "Python.Python.3.11")) {
      $tried += "winget $pkg"
      Write-Host "[nlm] 正在通过 winget 安装 $pkg （用户范围）..." -ForegroundColor Cyan
      Write-Host "      winget install -e --id $pkg --scope user"
      $wgArgs = @(
        "install", "-e", "--id", $pkg,
        "--scope", "user",
        "--accept-package-agreements",
        "--accept-source-agreements"
      )
      try {
        & winget @wgArgs
      } catch {
        Write-Host "[nlm] winget 调用异常: $($_.Exception.Message)" -ForegroundColor Yellow
      }
      Write-Host "[nlm] winget 退出码 $LASTEXITCODE ，重新扫描 Python..."
      Update-NlmProcessPath
      $found = Find-NlmPython
      if ($found) {
        Write-Host "[nlm] 已找到 Python: $found" -ForegroundColor Green
        return $found
      }
    }
  } else {
    $tried += "winget (not installed)"
    Write-Host "[nlm] 未找到 winget，无法自动安装。" -ForegroundColor Yellow
  }

  Write-Host "[nlm] 已尝试: $($tried -join '; ')" -ForegroundColor Yellow
  Write-Host "[nlm] 打开官网下载页。安装时请勾选 Add python.exe to PATH" -ForegroundColor Yellow
  try { Start-Process "https://www.python.org/downloads/" } catch { }
  return $null
}

function Resolve-NlmPython {
  Update-NlmProcessPath
  $found = Find-NlmPython
  if ($found) { return $found }

  Write-NlmMissingPython

  if (Test-NlmNonInteractive) {
    Write-NlmInstallHint
    return $null
  }

  while ($true) {
    Write-Host "[1] 自动安装 Python 3.12（推荐）"
    Write-Host "[2] 打开说明 / 下载页，我自己装"
    Write-Host "[3] 退出"
    Write-Host ""
    $choice = $null
    try {
      $choice = Read-Host "请选择 [1/2/3]"
    } catch {
      Write-Host "[nlm] 无法读取输入（非交互），退出。" -ForegroundColor Yellow
      return $null
    }
    $choice = ([string]$choice).Trim()
    if (-not $choice) {
      Write-Host "[nlm] 未输入选项（非交互或已取消），退出。" -ForegroundColor Yellow
      return $null
    }
    if ($choice -eq "1") {
      $found = Install-NlmPython
      if ($found) { return $found }
      Write-Host "[nlm] 安装后仍未找到 Python。若刚装完，可重试 1 或重新打开此窗口。" -ForegroundColor Yellow
      Write-Host ""
      continue
    }
    if ($choice -eq "2") {
      Write-Host "[nlm] 打开 https://www.python.org/downloads/"
      Write-Host "      安装时请勾选 Add python.exe to PATH"
      try { Start-Process "https://www.python.org/downloads/" } catch { }
      Write-Host "装好后重新运行 nlm，或按 1 再试。"
      Write-Host ""
      continue
    }
    if ($choice -eq "3") {
      Write-Host "[nlm] 已退出。安装 Python 3.10-3.13 后重新运行 nlm。"
      return $null
    }
    Write-Host "[nlm] 请输入 1、2 或 3"
  }
}

if (-not (Test-Path -LiteralPath $Boot)) {
  Write-Host "[nlm] Missing scripts\nlm_boot.py" -ForegroundColor Red
  if ($EnsurePythonOnly) { exit 1 }
  Wait-NlmIfClosing
  exit 1
}

$py = Resolve-NlmPython
if (-not $py) {
  if ($EnsurePythonOnly) { exit 1 }
  Wait-NlmIfClosing
  exit 1
}

if ($EnsurePythonOnly) {
  if ($env:NLM_PY_FILE) {
    Set-Content -LiteralPath $env:NLM_PY_FILE -Value $py -Encoding ascii
  } else {
    Write-Output $py
  }
  exit 0
}

if ($py -eq "py") {
  & py -3 $Boot @NlmArgs
} else {
  & $py $Boot @NlmArgs
}
exit $LASTEXITCODE
