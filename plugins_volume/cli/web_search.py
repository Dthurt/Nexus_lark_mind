#!/usr/bin/env python3
"""Web search CLI plugin for Nexus-Lark-Mind.

Input (stdin JSON):
  {"query": "...", "max_results": 5}

Provider priority:
  1) Tavily       — TAVILY_API_KEY   (https://github.com/tavily-ai/tavily-mcp)
  2) Brave Search — BRAVE_API_KEY    (https://github.com/brave/brave-search-mcp-server)
  3) DuckDuckGo   — free via `ddgs` (tries several backends)
  4) DDG Instant Answer API — free last-resort

Output (stdout JSON):
  {"ok": true, "provider": "...", "query": "...", "results": [...]}
"""

from __future__ import annotations

import json
import os
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Any, Callable, Dict, List

socket.setdefaulttimeout(18)


def _run_timeout(fn: Callable[..., Dict[str, Any]], *args: Any, timeout: float = 10.0) -> Dict[str, Any]:
    with ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(fn, *args)
        try:
            return fut.result(timeout=timeout)
        except FuturesTimeout as exc:
            raise TimeoutError(f"{fn.__name__} timed out after {timeout}s") from exc


def _read_input() -> Dict[str, Any]:
    raw = sys.stdin.read().strip() or "{}"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {"query": raw}
    return data if isinstance(data, dict) else {"query": str(data)}


def _normalize_results(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for it in items:
        out.append(
            {
                "title": it.get("title") or "",
                "url": it.get("url") or it.get("href") or it.get("link") or "",
                "snippet": it.get("content") or it.get("body") or it.get("snippet") or "",
            }
        )
    return [r for r in out if r["title"] or r["url"] or r["snippet"]]


def _http_json(url: str, *, data: Dict[str, Any] | None = None, headers: Dict[str, str] | None = None) -> Any:
    body = None
    req_headers = {"User-Agent": "Nexus-Lark-Mind/1.0", **(headers or {})}
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=body, headers=req_headers, method="POST" if body else "GET")
    with urllib.request.urlopen(req, timeout=40) as resp:
        return json.loads(resp.read().decode("utf-8"))


def search_tavily(query: str, max_results: int) -> Dict[str, Any]:
    api_key = os.environ.get("TAVILY_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("TAVILY_API_KEY missing")
    data = _http_json(
        "https://api.tavily.com/search",
        data={
            "api_key": api_key,
            "query": query,
            "search_depth": os.environ.get("TAVILY_SEARCH_DEPTH", "basic"),
            "include_answer": True,
            "max_results": max_results,
        },
    )
    return {
        "ok": True,
        "provider": "tavily",
        "query": query,
        "answer": data.get("answer"),
        "results": _normalize_results(list(data.get("results") or [])),
    }


def search_brave(query: str, max_results: int) -> Dict[str, Any]:
    api_key = os.environ.get("BRAVE_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("BRAVE_API_KEY missing")
    q = urllib.parse.urlencode({"q": query, "count": max_results})
    req = urllib.request.Request(
        f"https://api.search.brave.com/res/v1/web/search?{q}",
        headers={
            "Accept": "application/json",
            "X-Subscription-Token": api_key,
            "User-Agent": "Nexus-Lark-Mind/1.0",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=40) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    web = (data.get("web") or {}).get("results") or []
    rows = [
        {
            "title": r.get("title") or "",
            "url": r.get("url") or "",
            "snippet": r.get("description") or "",
        }
        for r in web
    ]
    return {"ok": True, "provider": "brave", "query": query, "answer": None, "results": rows}


def search_ddgs(query: str, max_results: int) -> Dict[str, Any]:
    try:
        from ddgs import DDGS
    except ImportError as exc:
        raise RuntimeError("ddgs package not installed. Run: pip install ddgs") from exc

    last_err: Exception | None = None
    # Keep backends short — some hang under restricted networks
    backends = ["duckduckgo", "yahoo"]
    with DDGS() as ddgs:
        for backend in backends:
            try:
                rows: List[Dict[str, Any]] = []
                for item in ddgs.text(query, max_results=max_results, backend=backend):
                    rows.append(
                        {
                            "title": item.get("title") or "",
                            "url": item.get("href") or item.get("url") or "",
                            "snippet": item.get("body") or "",
                        }
                    )
                if rows:
                    return {
                        "ok": True,
                        "provider": f"duckduckgo:{backend}",
                        "query": query,
                        "answer": None,
                        "results": rows,
                    }
            except Exception as exc:  # noqa: BLE001 — try next backend
                last_err = exc
                continue
    raise RuntimeError(str(last_err or "ddgs returned no results"))


def search_ddg_instant(query: str, max_results: int) -> Dict[str, Any]:
    """DuckDuckGo Instant Answer API — limited but free and often reachable."""
    q = urllib.parse.urlencode(
        {"q": query, "format": "json", "no_html": 1, "skip_disambig": 1}
    )
    req = urllib.request.Request(
        f"https://api.duckduckgo.com/?{q}",
        headers={"User-Agent": "Nexus-Lark-Mind/1.0"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=25) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    rows: List[Dict[str, Any]] = []
    abstract = (data.get("AbstractText") or "").strip()
    abstract_url = data.get("AbstractURL") or data.get("AbstractSource") or ""
    heading = data.get("Heading") or query
    if abstract:
        rows.append({"title": heading, "url": abstract_url, "snippet": abstract})

    for topic in data.get("RelatedTopics") or []:
        if len(rows) >= max_results:
            break
        if isinstance(topic, dict) and topic.get("Text"):
            rows.append(
                {
                    "title": (topic.get("Text") or "")[:80],
                    "url": topic.get("FirstURL") or "",
                    "snippet": topic.get("Text") or "",
                }
            )
        elif isinstance(topic, dict) and topic.get("Topics"):
            for sub in topic["Topics"]:
                if len(rows) >= max_results:
                    break
                if sub.get("Text"):
                    rows.append(
                        {
                            "title": (sub.get("Text") or "")[:80],
                            "url": sub.get("FirstURL") or "",
                            "snippet": sub.get("Text") or "",
                        }
                    )

    if not rows:
        raise RuntimeError("DuckDuckGo Instant Answer empty")
    return {
        "ok": True,
        "provider": "duckduckgo_instant",
        "query": query,
        "answer": abstract or None,
        "results": rows[:max_results],
    }


def main() -> None:
    data = _read_input()
    query = str(data.get("query") or data.get("q") or "").strip()
    if not query:
        print(json.dumps({"ok": False, "error": "query is required"}, ensure_ascii=False))
        sys.exit(2)

    try:
        max_results = int(data.get("max_results") or data.get("limit") or 5)
    except (TypeError, ValueError):
        max_results = 5
    max_results = max(1, min(max_results, 10))

    providers = [
        ("tavily", search_tavily, bool(os.environ.get("TAVILY_API_KEY", "").strip())),
        ("brave", search_brave, bool(os.environ.get("BRAVE_API_KEY", "").strip())),
        # Instant Answer first among free options — more reliable under restricted networks
        ("ddg_instant", search_ddg_instant, True),
        ("ddgs", search_ddgs, True),
    ]
    errors: List[str] = []
    for name, fn, enabled in providers:
        if not enabled:
            continue
        try:
            print(json.dumps(_run_timeout(fn, query, max_results, timeout=10.0), ensure_ascii=False))
            return
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{name}: {exc}")

    print(
        json.dumps(
            {
                "ok": False,
                "error": "all search providers failed",
                "detail": errors,
                "hint": "Set TAVILY_API_KEY (recommended) or BRAVE_API_KEY, and ensure network access",
            },
            ensure_ascii=False,
        )
    )
    sys.exit(1)


if __name__ == "__main__":
    main()
