#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
cp -n .env.example .env 2>/dev/null || true
mkdir -p data logs
docker compose up --build -d
docker compose ps
echo "Web UI: http://localhost:8000"
echo "Kernel RPC: http://localhost:8001/health"
echo "Orchestrator: http://localhost:8002/health"
