# Nexus-Lark-Mind local start / stop / status (no Docker / Redis)
param(
  [Parameter(Position = 0)]
  [ValidateSet("start", "stop", "status", "help")]
  [string]$Action = "start",

  [switch]$Open,
  [switch]$Install,
  [switch]$SkipInstall,
  [switch]$Quiet
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
$Root = (Get-Location).Path
$ReqHashFile = Join-Path $Root ".venv\.nlm_req_hash"

function Write-Step([string]$Message) {
  if (-not $Quiet) { Write-Host $Message }
}

function Get-PortPids([int]$Port) {
  $pids = @(
    Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
      Select-Object -ExpandProperty OwningProcess -Unique
  )
  if (-not $pids) {
    $lines = netstat -ano | Select-String ":$Port\s+.*LISTENING"
    foreach ($line in $lines) {
      $parts = ($line.ToString() -split "\s+") | Where-Object { $_ }
      if ($parts.Count -ge 5) { $pids += [int]$parts[-1] }
    }
    $pids = @($pids | Select-Object -Unique)
  }
  return @($pids | Where-Object { $_ -and $_ -ne 0 })
}

function Free-LocalPorts {
  $killed = $false
  foreach ($port in 8000, 8001, 8002) {
    foreach ($procId in (Get-PortPids $port)) {
      Write-Step "  Killing PID $procId on port $port"
      Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
      $killed = $true
    }
  }
  if (-not $killed) {
    Write-Step "  Ports 8000/8001/8002 already free."
  }
}

function Test-LocalHealth {
  $ok = $true
  foreach ($item in @(
      @{ Name = "Web/Adapters"; Url = "http://127.0.0.1:8000/health" },
      @{ Name = "Kernel"; Url = "http://127.0.0.1:8001/health" },
      @{ Name = "Orchestrator"; Url = "http://127.0.0.1:8002/health" }
    )) {
    try {
      $res = Invoke-WebRequest -Uri $item.Url -UseBasicParsing -TimeoutSec 2
      if ($res.StatusCode -ge 200 -and $res.StatusCode -lt 300) {
        Write-Host ("  OK  {0,-14} {1}" -f $item.Name, $item.Url) -ForegroundColor Green
      } else {
        Write-Host ("  FAIL {0,-14} HTTP {1}" -f $item.Name, $res.StatusCode) -ForegroundColor Red
        $ok = $false
      }
    } catch {
      Write-Host ("  DOWN {0,-14} {1}" -f $item.Name, $item.Url) -ForegroundColor Yellow
      $ok = $false
    }
  }
  return $ok
}

function Resolve-Python {
  $candidates = @(
    "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe"
  )
  $py = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
  if (-not $py) {
    $py = (Get-Command python -ErrorAction SilentlyContinue | Where-Object { $_.Source -notmatch "WindowsApps" }).Source
  }
  if (-not $py) {
    Write-Error "Python 3.11+ not found. Install from https://www.python.org/downloads/ (check Add python.exe to PATH)."
  }
  return $py
}

function Get-ReqHash {
  $req = Join-Path $Root "requirements.txt"
  if (-not (Test-Path $req)) { return "" }
  $algo = [System.Security.Cryptography.SHA256]::Create()
  try {
    $bytes = [System.IO.File]::ReadAllBytes($req)
    return ([BitConverter]::ToString($algo.ComputeHash($bytes)) -replace "-", "").ToLowerInvariant()
  } finally {
    $algo.Dispose()
  }
}

function Ensure-Venv([string]$Python) {
  if (-not (Test-Path (Join-Path $Root ".venv\Scripts\python.exe"))) {
    Write-Step "Creating venv..."
    & $Python -m venv (Join-Path $Root ".venv")
  }

  $wantInstall = $false
  if ($Install) {
    $wantInstall = $true
  } elseif ($SkipInstall) {
    $wantInstall = $false
  } else {
    $hash = Get-ReqHash
    $prev = if (Test-Path $ReqHashFile) { (Get-Content $ReqHashFile -Raw).Trim() } else { "" }
    if (-not $hash -or $hash -ne $prev) { $wantInstall = $true }
  }

  if ($wantInstall) {
    Write-Step "Installing Python deps (requirements.txt)..."
    & (Join-Path $Root ".venv\Scripts\python.exe") -m pip install -q --upgrade pip
    & (Join-Path $Root ".venv\Scripts\python.exe") -m pip install -q -r (Join-Path $Root "requirements.txt")
    $hash = Get-ReqHash
    if ($hash) {
      New-Item -ItemType Directory -Force -Path (Split-Path $ReqHashFile) | Out-Null
      Set-Content -Path $ReqHashFile -Value $hash -NoNewline
    }
  } else {
    Write-Step "Deps OK (skip pip — use -Install to force)."
  }
}

function Set-LocalEnv {
  $env:KERNEL_RPC_URL = "http://127.0.0.1:8001"
  $env:ORCHESTRATOR_RPC_URL = "http://127.0.0.1:8002"
  $env:REDIS_URL = "memory://local"
  $env:PLUGINS_DIR = "plugins_volume"
  $env:WEB_STATIC_DIR = "web-static"
  $env:DATABASE_URL = "sqlite+aiosqlite:///data/nexus.db"
  $env:PYTHONPATH = $Root
}

if ($Action -eq "help") {
  Write-Host @"
Usage: .\scripts\start_local.ps1 [start|stop|status|help] [-Open] [-Install] [-SkipInstall]

  start        Start local all-in-one stack (default)
  stop         Free ports 8000/8001/8002
  status       Health-check the three services
  help         Show this help

  -Open        Open http://127.0.0.1:8000 after healthy
  -Install     Force pip install -r requirements.txt
  -SkipInstall Never pip install this run

Frontend HMR debug: .\scripts\dev.ps1
Rebuild static UI:  .\scripts\build_web.bat
Premium wizard:     .\nlm.ps1   (or nlm.cmd)
Docs: docs\local-start.md
"@
  exit 0
}

if ($Action -eq "stop") {
  if (-not $Quiet) { Write-Host "=== Nexus-Lark-Mind local stop ===" }
  Free-LocalPorts
  if (-not $Quiet) { Write-Host "Stopped." }
  exit 0
}

if ($Action -eq "status") {
  Write-Host "=== Nexus-Lark-Mind local status ==="
  if (Test-LocalHealth) {
    Write-Host "All services healthy." -ForegroundColor Green
    exit 0
  }
  Write-Host "One or more services are down. Start with: .\scripts\start_local.ps1" -ForegroundColor Yellow
  exit 1
}

# ---- start ----
Write-Host "=== Nexus-Lark-Mind local start ==="

$py = Resolve-Python
Write-Step "Using: $py"
& $py --version

Ensure-Venv $py

if (-not (Test-Path (Join-Path $Root ".env"))) {
  Copy-Item (Join-Path $Root ".env.example") (Join-Path $Root ".env")
  Write-Step "Created .env from .env.example — fill model keys if needed."
}
New-Item -ItemType Directory -Force -Path (Join-Path $Root "data"), (Join-Path $Root "logs") | Out-Null

if (-not (Test-Path (Join-Path $Root "web-static\index.html"))) {
  Write-Host "WARN: web-static\index.html missing. Build UI with scripts\build_web.bat" -ForegroundColor Yellow
  Write-Host "      Or use scripts\dev.ps1 for Vite HMR (http://127.0.0.1:5173)." -ForegroundColor Yellow
}

Write-Step "Freeing ports 8000/8001/8002 if busy..."
Free-LocalPorts
Set-LocalEnv

Write-Host ""
Write-Host "Web UI:        http://127.0.0.1:8000   (built React → web-static)"
Write-Host "Kernel:        http://127.0.0.1:8001/health"
Write-Host "Orchestrator:  http://127.0.0.1:8002/health"
Write-Host "Broker:        memory://local"
Write-Host "Frontend HMR:  .\scripts\dev.ps1   → http://127.0.0.1:5173"
Write-Host "Ctrl+C to stop, or: .\scripts\start_local.ps1 stop"
Write-Host ""

if ($Open) {
  Start-Job -ScriptBlock {
    for ($i = 0; $i -lt 60; $i++) {
      Start-Sleep -Seconds 1
      try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -UseBasicParsing -TimeoutSec 1
        if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 300) {
          Start-Process "http://127.0.0.1:8000"
          return
        }
      } catch { }
    }
  } | Out-Null
}

& (Join-Path $Root ".venv\Scripts\python.exe") -m src.entry_local
