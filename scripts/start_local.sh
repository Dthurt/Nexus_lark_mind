#!/usr/bin/env bash
# Cross-platform local start (Linux / macOS) — thin wrapper → ./nlm
# Usage: ./scripts/start_local.sh [start|stop|status|help] [--open]
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NLM="$ROOT/nlm"

if [[ ! -x "$NLM" ]]; then
  chmod +x "$NLM" 2>/dev/null || true
fi

ACTION="${1:-start}"
shift || true

case "$ACTION" in
  help|-h|--help)
    cat <<'EOF'
Usage: ./scripts/start_local.sh [start|stop|status|help] [--open]

  start   One-shot setup + launch (via nlm)
  stop    Free ports 8000/8001/8002
  status  Health / doctor check
  help    Show this help

  --open  Open browser after healthy (start only)

Preferred entry: ./nlm   |   ./nlm start
Frontend HMR:   ./scripts/dev.sh
EOF
    exit 0
    ;;
  stop)
    exec "$NLM" stop
    ;;
  status)
    exec "$NLM" status
    ;;
  start|"")
    EXTRA=()
    for arg in "$@"; do
      case "$arg" in
        --open|-Open|-open) EXTRA+=() ;; # nlm opens by default
        --no-open) EXTRA+=(--no-open) ;;
        --skip-setup) EXTRA+=(--skip-setup) ;;
      esac
    done
    # If user passed --open explicitly it's already default; honor --no-open
    if printf '%s\n' "$@" | grep -Eq -- '^--no-open$'; then
      exec "$NLM" start --no-open "${EXTRA[@]}"
    fi
    exec "$NLM" start "${EXTRA[@]}"
    ;;
  *)
    echo "Unknown action: $ACTION (try: start|stop|status|help)" >&2
    exit 2
    ;;
esac
