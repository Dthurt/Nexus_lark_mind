# Nexus-Lark-Mind local start (no Docker / Redis)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

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
Write-Host "Ctrl+C to stop"
Write-Host ""

& .\.venv\Scripts\python.exe -m src.entry_local
