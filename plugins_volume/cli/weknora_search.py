#!/usr/bin/env python3
"""Optional WeKnora HTTP read-only search — no-op unless WEKNORA_BASE_URL is set.

CLI plugin auto-registered when present under plugins_volume/cli/.
Does not replace the local SQLite knowledge base.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


def main() -> int:
    raw = sys.stdin.read() or "{}"
    try:
        args = json.loads(raw)
    except json.JSONDecodeError:
        args = {}
    query = str(args.get("query") or "").strip()
    base = (os.getenv("WEKNORA_BASE_URL") or "").strip().rstrip("/")
    api_key = (os.getenv("WEKNORA_API_KEY") or "").strip()
    if not base:
        print(
            json.dumps(
                {
                    "ok": True,
                    "skipped": True,
                    "reason": "WEKNORA_BASE_URL not set — local KB remains default",
                    "results": [],
                }
            )
        )
        return 0
    if not query:
        print(json.dumps({"ok": False, "error": "query required", "results": []}))
        return 1
    # Best-effort OpenAPI-ish search; adjust path when wiring a real WeKnora deploy.
    path = os.getenv("WEKNORA_SEARCH_PATH") or "/api/v1/search"
    url = f"{base}{path}?{urllib.parse.urlencode({'q': query, 'limit': int(args.get('limit') or 5)})}"
    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8", errors="replace")
        data = json.loads(body)
        print(json.dumps({"ok": True, "source": "weknora", "query": query, "data": data}))
        return 0
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc), "results": []}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
