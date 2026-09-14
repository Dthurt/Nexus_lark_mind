# Local debug: backend (memory broker) + Vite HMR frontend
param(
  [switch]$Install,
  [switch]$SkipInstall,
  [switch]$NoOpen,
  [switch]$BackendOnly,
  [switch]$FrontendOnly
)

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
Set-Location $Root

function Resolve-Node {
  $portable = Join-Path $Root ".tools\node\node-v22.14.0-win-x64"
  if (Test-Path (Join-Path $portable "node.exe")) {
    $env:PATH = "$portable;$env:PATH"
  }
  $node = Get-Command node -ErrorAction SilentlyContinue
  if (-not $node) {
    Write-Error "Node.js 20+ not found. Install LTS or place portable Node under .tools\node\"
  }
  return $node.Source
}

Write-Host "=== Nexus-Lark-Mind local DEBUG ==="
Write-Host "Backend API : http://127.0.0.1:8000"
Write-Host "Vite UI     : http://127.0.0.1:5173  ← open this while debugging UI"
Write-Host "Stop        : Ctrl+C (stops Vite; then run .\scripts\start_local.ps1 stop)"
Write-Host ""

$backendProc = $null
$viteProc = $null

function Stop-DebugChildren {
  if ($viteProc -and -not $viteProc.HasExited) {
    Stop-Process -Id $viteProc.Id -Force -ErrorAction SilentlyContinue
  }
  if ($backendProc -and -not $backendProc.HasExited) {
    Stop-Process -Id $backendProc.Id -Force -ErrorAction SilentlyContinue
  }
  # Also free known ports in case child trees linger
  & (Join-Path $PSScriptRoot "start_local.ps1") stop -Quiet 2>$null
}

try {
  if (-not $FrontendOnly) {
    $startArgs = @("start")
    if ($Install) { $startArgs += "-Install" }
    if ($SkipInstall) { $startArgs += "-SkipInstall" }

    Write-Host "Starting backend (detached)..."
    $argList = @(
      "-NoProfile", "-ExecutionPolicy", "Bypass",
      "-File", (Join-Path $PSScriptRoot "start_local.ps1")
    ) + $startArgs
    $backendProc = Start-Process -FilePath "powershell" -ArgumentList $argList `
      -WorkingDirectory $Root -PassThru -WindowStyle Minimized

    Write-Host "Waiting for backend health..."
    $ready = $false
    for ($i = 0; $i -lt 90; $i++) {
      Start-Sleep -Seconds 1
      try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -UseBasicParsing -TimeoutSec 1
        if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 300) {
          $ready = $true
          break
        }
      } catch { }
      if ($backendProc.HasExited) {
        Write-Error "Backend exited early (code $($backendProc.ExitCode)). Check the minimized PowerShell window / logs."
      }
    }
    if (-not $ready) {
      Write-Error "Backend did not become healthy on :8000 within 90s."
    }
    Write-Host "Backend OK." -ForegroundColor Green
  }

  if ($BackendOnly) {
    Write-Host "Backend-only mode. Press Enter to stop..."
    [void][Console]::ReadLine()
    exit 0
  }

  Resolve-Node | Out-Null
  Set-Location (Join-Path $Root "web")
  if (-not (Test-Path "node_modules")) {
    Write-Host "npm install..."
    npm install
    if ($LASTEXITCODE -ne 0) { Write-Error "npm install failed" }
  }

  if (-not $NoOpen) {
    Start-Job -ScriptBlock {
      Start-Sleep -Seconds 2
      Start-Process "http://127.0.0.1:5173"
    } | Out-Null
  }

  Write-Host "Starting Vite..."
  # Foreground npm so Ctrl+C reaches it; finally block cleans backend
  npm run dev
} finally {
  Write-Host ""
  Write-Host "Cleaning up debug processes..."
  Stop-DebugChildren
  Write-Host "Done."
}
