#!/usr/bin/env bash
# Local debug: backend (memory broker) + Vite HMR frontend (Linux / macOS)
# Usage: ./scripts/dev.sh [--no-open] [--backend-only] [--frontend-only]
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

NO_OPEN=0
BACKEND_ONLY=0
FRONTEND_ONLY=0
for arg in "$@"; do
  case "$arg" in
    --no-open|-NoOpen) NO_OPEN=1 ;;
    --backend-only|-BackendOnly) BACKEND_ONLY=1 ;;
    --frontend-only|-FrontendOnly) FRONTEND_ONLY=1 ;;
  esac
done

cleanup() {
  echo ""
  echo "Cleaning up debug processes…"
  if [[ -n "${VITE_PID:-}" ]] && kill -0 "$VITE_PID" 2>/dev/null; then
    kill "$VITE_PID" 2>/dev/null || true
  fi
  if [[ -n "${BACKEND_PID:-}" ]] && kill -0 "$BACKEND_PID" 2>/dev/null; then
    kill "$BACKEND_PID" 2>/dev/null || true
  fi
  "$ROOT/nlm" stop >/dev/null 2>&1 || true
  echo "Done."
}
trap cleanup EXIT INT TERM

echo "=== Nexus-Lark-Mind local DEBUG ==="
echo "Backend API : http://127.0.0.1:8000"
echo "Vite UI     : http://127.0.0.1:5173  ← open this while debugging UI"
echo "Stop        : Ctrl+C"
echo ""

if [[ "$FRONTEND_ONLY" -eq 0 ]]; then
  echo "Starting backend…"
  "$ROOT/nlm" start --no-open &
  BACKEND_PID=$!
  echo "Waiting for backend health…"
  ready=0
  for _ in $(seq 1 90); do
    if curl -sf "http://127.0.0.1:8000/health" >/dev/null 2>&1; then
      ready=1
      break
    fi
    if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
      echo "Backend exited early." >&2
      exit 1
    fi
    sleep 1
  done
  if [[ "$ready" -ne 1 ]]; then
    echo "Backend did not become healthy on :8000 within 90s." >&2
    exit 1
  fi
  echo "Backend OK."
fi

if [[ "$BACKEND_ONLY" -eq 1 ]]; then
  echo "Backend-only mode. Press Enter to stop…"
  read -r _
  exit 0
fi

if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
  echo "Node.js 20+ not found. Install LTS: https://nodejs.org/" >&2
  exit 1
fi

NODE_MAJOR="$(node --version | sed -E 's/^v([0-9]+).*/\1/')"
if [[ "$NODE_MAJOR" -lt 18 ]]; then
  echo "Node v$NODE_MAJOR is too old — need 18+ (prefer 20 LTS)." >&2
  exit 1
fi

cd "$ROOT/web"
if [[ ! -d node_modules ]]; then
  echo "npm install…"
  npm install
fi

if [[ "$NO_OPEN" -eq 0 ]]; then
  (sleep 2 && (xdg-open "http://127.0.0.1:5173" 2>/dev/null || open "http://127.0.0.1:5173" 2>/dev/null || true)) &
fi

echo "Starting Vite…"
npm run dev &
VITE_PID=$!
wait "$VITE_PID"
