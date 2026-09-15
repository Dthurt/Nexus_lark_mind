# Nexus Lark Mind — one-command local console
# Usage: .\nlm.ps1 | .\nlm.ps1 start | setup | config | crawl | status | stop | repair

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Boot = Join-Path $Root "scripts\nlm_boot.py"
$VenvPy = Join-Path $Root ".venv\Scripts\python.exe"

if (-not (Test-Path $Boot)) {
  Write-Host "[nlm] Missing scripts\nlm_boot.py" -ForegroundColor Red
  exit 1
}

function Find-Python {
  if (Test-Path $VenvPy) { return $VenvPy }
  $candidates = @(
    "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe"
  )
  foreach ($c in $candidates) {
    if (Test-Path $c) { return $c }
  }
  $cmd = Get-Command python -ErrorAction SilentlyContinue
  if ($cmd -and $cmd.Source -notmatch "WindowsApps") { return $cmd.Source }
  $py = Get-Command py -ErrorAction SilentlyContinue
  if ($py) { return "py" }
  return $null
}

$py = Find-Python
if (-not $py) {
  Write-Host "[nlm] Python 3.11+ not found. https://www.python.org/downloads/" -ForegroundColor Red
  exit 1
}

if ($py -eq "py") {
  & py -3 $Boot @args
} else {
  & $py $Boot @args
}
exit $LASTEXITCODE
