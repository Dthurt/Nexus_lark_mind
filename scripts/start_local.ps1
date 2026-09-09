# Nexus-Lark-Mind local start/stop (no Docker / Redis)
param(
  [Parameter(Position = 0)]
  [ValidateSet("start", "stop", "help")]
  [string]$Action = "start"
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

function Free-LocalPorts {
  $killed = $false
  foreach ($port in 8000, 8001, 8002) {
    $pids = @(
      Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique
    )
    if (-not $pids) {
      # Fallback when Get-NetTCPConnection is unavailable
      $lines = netstat -ano | Select-String ":$port\s+.*LISTENING"
      foreach ($line in $lines) {
        $parts = ($line.ToString() -split "\s+") | Where-Object { $_ }
        if ($parts.Count -ge 5) { $pids += [int]$parts[-1] }
      }
      $pids = $pids | Select-Object -Unique
    }
    foreach ($procId in $pids) {
      if ($procId -and $procId -ne 0) {
        Write-Host "  Killing PID $procId on port $port"
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
        $killed = $true
      }
    }
  }
  if (-not $killed) {
    Write-Host "  Ports 8000/8001/8002 already free."
  }
}

if ($Action -eq "help") {
  Write-Host "Usage: .\scripts\start_local.ps1 [start|stop]"
  Write-Host "  start  Start local services (default)"
  Write-Host "  stop   Stop services on ports 8000/8001/8002"
  exit 0
}

if ($Action -eq "stop") {
  Write-Host "=== Nexus-Lark-Mind local stop ==="
  Free-LocalPorts
  Write-Host "Stopped."
  exit 0
}

Write-Host "=== Nexus-Lark-Mind local start ==="

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
  Write-Error "Python 3.11+ not found. Install from https://www.python.org/downloads/"
}

Write-Host "Using: $py"
& $py --version

if (-not (Test-Path .venv)) {
  Write-Host "Creating venv..."
  & $py -m venv .venv
}

& .\.venv\Scripts\python.exe -m pip install -q --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -q -r requirements.txt

if (-not (Test-Path .env)) { Copy-Item .env.example .env }
New-Item -ItemType Directory -Force -Path data, logs | Out-Null

Write-Host "Freeing ports 8000/8001/8002 if busy..."
Free-LocalPorts

$env:KERNEL_RPC_URL = "http://127.0.0.1:8001"
$env:ORCHESTRATOR_RPC_URL = "http://127.0.0.1:8002"
$env:REDIS_URL = "memory://local"
$env:PLUGINS_DIR = "plugins_volume"
$env:WEB_STATIC_DIR = "web-static"
$env:DATABASE_URL = "sqlite+aiosqlite:///data/nexus.db"
$env:PYTHONPATH = (Get-Location).Path

Write-Host ""
Write-Host "Web UI:        http://127.0.0.1:8000"
Write-Host "Kernel:        http://127.0.0.1:8001/health"
Write-Host "Orchestrator:  http://127.0.0.1:8002/health"
Write-Host "Broker:        memory://local"
Write-Host "Ctrl+C to stop, or: .\scripts\start_local.ps1 stop"
Write-Host ""

& .\.venv\Scripts\python.exe -m src.entry_local
