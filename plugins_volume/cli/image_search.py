#!/usr/bin/env python3
"""Image search CLI plugin for Nexus-Lark-Mind.

Input (stdin JSON):
  {"query": "...", "max_results": 6}

Provider priority (first configured wins):
  1) SerpAPI Google Images — SERPAPI_API_KEY
  2) Bing Image Search    — BING_SEARCH_API_KEY (Azure)
  3) Brave Images         — BRAVE_API_KEY
  4) Unsplash             — UNSPLASH_ACCESS_KEY
  5) Pexels               — PEXELS_API_KEY
  6) DuckDuckGo Images    — free via `ddgs` (optional)

Output (stdout JSON):
  {
    "ok": true,
    "provider": "...",
    "query": "...",
    "results": [{"title","url","thumb","source","width","height"}],
    "markdown": "![...](url)\\n...",
    "hint": "Paste markdown into the assistant reply so images render in chat."
  }
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

socket.setdefaulttimeout(20)


def _run_timeout(fn: Callable[..., Dict[str, Any]], *args: Any, timeout: float = 14.0) -> Dict[str, Any]:
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


def _http_json(
    url: str,
    *,
    data: Dict[str, Any] | None = None,
    headers: Dict[str, str] | None = None,
    method: str | None = None,
) -> Any:
    body = None
    req_headers = {"User-Agent": "Nexus-Lark-Mind/1.0", **(headers or {})}
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(
        url,
        data=body,
        headers=req_headers,
        method=method or ("POST" if body else "GET"),
    )
    with urllib.request.urlopen(req, timeout=40) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _normalize(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen = set()
    for it in items:
        url = (it.get("url") or it.get("image") or it.get("original") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(
            {
                "title": (it.get("title") or it.get("alt") or it.get("description") or "")[:120],
                "url": url,
                "thumb": (it.get("thumb") or it.get("thumbnail") or url)[:2000],
                "source": it.get("source") or it.get("link") or it.get("page_url") or "",
                "width": it.get("width"),
                "height": it.get("height"),
            }
        )
    return out


def _pack(provider: str, query: str, results: List[Dict[str, Any]]) -> Dict[str, Any]:
    rows = _normalize(results)
    lines = []
    for i, r in enumerate(rows, 1):
        alt = (r["title"] or f"{query} {i}").replace("]", "").replace("[", "")[:80]
        lines.append(f"![{alt}]({r['url']})")
        if r.get("source"):
            lines.append(f"[来源]({r['source']})")
    md = "\n\n".join(lines)
    return {
        "ok": True,
        "provider": provider,
        "query": query,
        "results": rows,
        "markdown": md,
        "hint": "把 markdown 字段整段贴进助手回复，聊天里会渲染图片画廊。",
    }


def search_serpapi(query: str, max_results: int) -> Dict[str, Any]:
    key = os.environ.get("SERPAPI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("SERPAPI_API_KEY missing")
    q = urllib.parse.urlencode(
        {
            "engine": "google_images",
            "q": query,
            "api_key": key,
            "num": max_results,
            "hl": "zh-cn",
            "gl": "cn",
        }
    )
    data = _http_json(f"https://serpapi.com/search.json?{q}")
    rows = []
    for r in list(data.get("images_results") or [])[:max_results]:
        rows.append(
            {
                "title": r.get("title") or "",
                "url": r.get("original") or r.get("thumbnail") or "",
                "thumb": r.get("thumbnail") or "",
                "source": r.get("link") or r.get("source") or "",
                "width": r.get("original_width"),
                "height": r.get("original_height"),
            }
        )
    if not rows:
        raise RuntimeError("SerpAPI returned no images")
    return _pack("serpapi", query, rows)


def search_bing(query: str, max_results: int) -> Dict[str, Any]:
    key = os.environ.get("BING_SEARCH_API_KEY", "").strip() or os.environ.get(
        "AZURE_BING_SEARCH_KEY", ""
    ).strip()
    if not key:
        raise RuntimeError("BING_SEARCH_API_KEY missing")
    endpoint = (
        os.environ.get("BING_SEARCH_ENDPOINT", "").strip()
        or "https://api.bing.microsoft.com/v7.0/images/search"
    )
    q = urllib.parse.urlencode({"q": query, "count": max_results, "mkt": "zh-CN"})
    data = _http_json(
        f"{endpoint}?{q}",
        headers={"Ocp-Apim-Subscription-Key": key},
    )
    rows = []
    for r in list(data.get("value") or [])[:max_results]:
        rows.append(
            {
                "title": r.get("name") or "",
                "url": r.get("contentUrl") or "",
                "thumb": r.get("thumbnailUrl") or "",
                "source": r.get("hostPageUrl") or "",
                "width": r.get("width"),
                "height": r.get("height"),
            }
        )
    if not rows:
        raise RuntimeError("Bing returned no images")
    return _pack("bing", query, rows)


def search_brave_images(query: str, max_results: int) -> Dict[str, Any]:
    key = os.environ.get("BRAVE_API_KEY", "").strip()
    if not key:
        raise RuntimeError("BRAVE_API_KEY missing")
    q = urllib.parse.urlencode({"q": query, "count": max_results})
    data = _http_json(
        f"https://api.search.brave.com/res/v1/images/search?{q}",
        headers={
            "Accept": "application/json",
            "X-Subscription-Token": key,
        },
    )
    rows = []
    for r in list(data.get("results") or [])[:max_results]:
        props = r.get("properties") or {}
        rows.append(
            {
                "title": r.get("title") or "",
                "url": props.get("url") or r.get("url") or "",
                "thumb": (r.get("thumbnail") or {}).get("src") if isinstance(r.get("thumbnail"), dict) else r.get("thumbnail") or "",
                "source": r.get("url") or "",
                "width": props.get("width"),
                "height": props.get("height"),
            }
        )
    if not rows:
        raise RuntimeError("Brave Images returned no images")
    return _pack("brave_images", query, rows)


def search_unsplash(query: str, max_results: int) -> Dict[str, Any]:
    key = os.environ.get("UNSPLASH_ACCESS_KEY", "").strip()
    if not key:
        raise RuntimeError("UNSPLASH_ACCESS_KEY missing")
    q = urllib.parse.urlencode({"query": query, "per_page": max_results})
    data = _http_json(
        f"https://api.unsplash.com/search/photos?{q}",
        headers={"Authorization": f"Client-ID {key}", "Accept-Version": "v1"},
    )
    rows = []
    for r in list(data.get("results") or [])[:max_results]:
        urls = r.get("urls") or {}
        user = (r.get("user") or {}).get("name") or ""
        rows.append(
            {
                "title": r.get("description") or r.get("alt_description") or user or query,
                "url": urls.get("regular") or urls.get("full") or urls.get("small") or "",
                "thumb": urls.get("small") or urls.get("thumb") or "",
                "source": r.get("links", {}).get("html") if isinstance(r.get("links"), dict) else "",
                "width": r.get("width"),
                "height": r.get("height"),
            }
        )
    if not rows:
        raise RuntimeError("Unsplash returned no images")
    return _pack("unsplash", query, rows)


def search_pexels(query: str, max_results: int) -> Dict[str, Any]:
    key = os.environ.get("PEXELS_API_KEY", "").strip()
    if not key:
        raise RuntimeError("PEXELS_API_KEY missing")
    q = urllib.parse.urlencode({"query": query, "per_page": max_results})
    data = _http_json(
        f"https://api.pexels.com/v1/search?{q}",
        headers={"Authorization": key},
    )
    rows = []
    for r in list(data.get("photos") or [])[:max_results]:
        src = r.get("src") or {}
        rows.append(
            {
                "title": r.get("alt") or query,
                "url": src.get("large") or src.get("original") or src.get("medium") or "",
                "thumb": src.get("medium") or src.get("small") or "",
                "source": r.get("url") or "",
                "width": r.get("width"),
                "height": r.get("height"),
            }
        )
    if not rows:
        raise RuntimeError("Pexels returned no images")
    return _pack("pexels", query, rows)


def search_ddgs(query: str, max_results: int) -> Dict[str, Any]:
    try:
        from ddgs import DDGS  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"ddgs not installed: {exc}") from exc
    rows = []
    with DDGS() as ddgs:
        for r in ddgs.images(query, max_results=max_results) or []:
            rows.append(
                {
                    "title": r.get("title") or "",
                    "url": r.get("image") or r.get("url") or "",
                    "thumb": r.get("thumbnail") or "",
                    "source": r.get("url") or r.get("source") or "",
                    "width": r.get("width"),
                    "height": r.get("height"),
                }
            )
    if not rows:
        raise RuntimeError("DuckDuckGo images returned no results")
    return _pack("ddgs", query, rows)


PROVIDERS = [
    ("SERPAPI_API_KEY", search_serpapi),
    ("BING_SEARCH_API_KEY", search_bing),
    ("AZURE_BING_SEARCH_KEY", search_bing),
    ("BRAVE_API_KEY", search_brave_images),
    ("UNSPLASH_ACCESS_KEY", search_unsplash),
    ("PEXELS_API_KEY", search_pexels),
]


def main() -> int:
    payload = _read_input()
    query = str(payload.get("query") or "").strip()
    if not query:
        print(json.dumps({"ok": False, "error": "query required"}, ensure_ascii=False))
        return 1
    try:
        max_results = int(payload.get("max_results") or 6)
    except (TypeError, ValueError):
        max_results = 6
    max_results = max(1, min(max_results, 12))

    errors: List[str] = []
    tried = set()
    for env_key, fn in PROVIDERS:
        if not os.environ.get(env_key, "").strip():
            continue
        if fn in tried:
            continue
        tried.add(fn)
        try:
            result = _run_timeout(fn, query, max_results, timeout=16.0)
            print(json.dumps(result, ensure_ascii=False))
            return 0
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{fn.__name__}: {exc}")

    # Free fallback
    try:
        result = _run_timeout(search_ddgs, query, max_results, timeout=18.0)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as exc:  # noqa: BLE001
        errors.append(f"search_ddgs: {exc}")

    print(
        json.dumps(
            {
                "ok": False,
                "error": "No image search provider succeeded. "
                "Configure SERPAPI_API_KEY / BING_SEARCH_API_KEY / BRAVE_API_KEY / "
                "UNSPLASH_ACCESS_KEY / PEXELS_API_KEY in the plugin card.",
                "details": errors[:6],
                "query": query,
            },
            ensure_ascii=False,
        )
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
