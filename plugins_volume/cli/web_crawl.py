#!/usr/bin/env python3
"""Crawl a URL with Crawl4AI and return LLM-friendly Markdown.

Input (stdin JSON):
  {
    "url": "https://example.com",
    "max_chars": 40000,          # truncate markdown for context budget
    "wait_for": null,            # optional CSS selector to wait for
    "js": false                  # reserved; Crawl4AI always uses a browser
  }

Output (stdout JSON):
  {
    "ok": true,
    "provider": "crawl4ai",
    "url": "...",
    "title": "...",
    "markdown": "...",
    "links": [...],
    "truncated": false,
    "chars": 1234
  }
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
import os
import sys
from typing import Any, Dict, List, Optional

# Windows consoles often use GBK; Crawl4AI prints Unicode glyphs (✓) and crashes otherwise.
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("PYTHONUTF8", "1")
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass


def _read_input() -> Dict[str, Any]:
    raw = sys.stdin.read().strip() or "{}"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {"url": raw}
    return data if isinstance(data, dict) else {"url": str(data)}


def _truncate(text: str, max_chars: int) -> tuple[str, bool]:
    s = text or ""
    if max_chars <= 0 or len(s) <= max_chars:
        return s, False
    head = int(max_chars * 0.72)
    tail = max_chars - head - 80
    if tail < 200:
        return s[: max_chars - 40] + "\n…[truncated]…", True
    return (
        s[:head]
        + f"\n\n…[truncated {len(s) - max_chars} chars]…\n\n"
        + s[-tail:],
        True,
    )


def _links_from_result(result: Any, limit: int = 40) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    links = getattr(result, "links", None) or {}
    if isinstance(links, dict):
        for kind in ("internal", "external"):
            for item in links.get(kind) or []:
                if isinstance(item, dict):
                    href = item.get("href") or item.get("url") or ""
                    text = item.get("text") or item.get("title") or ""
                else:
                    href = str(item)
                    text = ""
                if href:
                    out.append({"url": href, "text": (text or "")[:120], "kind": kind})
                if len(out) >= limit:
                    return out
    return out


async def _crawl(url: str, *, wait_for: Optional[str] = None) -> Dict[str, Any]:
    try:
        from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
    except ImportError as exc:
        return {
            "ok": False,
            "error": "crawl4ai_not_installed",
            "detail": (
                "Crawl4AI is not installed in this Python env. "
                "Run: pip install crawl4ai && crawl4ai-setup"
            ),
            "hint": str(exc),
        }

    browser_cfg = BrowserConfig(headless=True, verbose=False)
    run_kwargs: Dict[str, Any] = {
        "word_count_threshold": 10,
        "exclude_external_links": False,
        "process_iframes": False,
        "remove_overlay_elements": True,
    }
    if wait_for:
        run_kwargs["wait_for"] = wait_for
    try:
        run_cfg = CrawlerRunConfig(**run_kwargs)
    except TypeError:
        # Older crawl4ai may not accept all kwargs
        run_cfg = CrawlerRunConfig()

    # Keep Crawl4AI progress banners off stdout so the CLI emits pure JSON.
    sink = io.StringIO()
    try:
        with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            async with AsyncWebCrawler(config=browser_cfg) as crawler:
                result = await crawler.arun(url=url, config=run_cfg)
    except Exception as exc:
        return {
            "ok": False,
            "error": "crawl_failed",
            "url": url,
            "detail": str(exc),
        }

    success = bool(getattr(result, "success", True))
    if not success:
        return {
            "ok": False,
            "error": "crawl_unsuccessful",
            "url": url,
            "detail": getattr(result, "error_message", None) or "unknown",
        }

    md = (
        getattr(result, "markdown", None)
        or getattr(result, "fit_markdown", None)
        or ""
    )
    if hasattr(md, "raw_markdown"):
        md = md.raw_markdown or str(md)
    elif not isinstance(md, str):
        md = str(md or "")

    title = ""
    meta = getattr(result, "metadata", None) or {}
    if isinstance(meta, dict):
        title = str(meta.get("title") or meta.get("og:title") or "")[:300]

    return {
        "ok": True,
        "provider": "crawl4ai",
        "url": url,
        "title": title,
        "markdown": md,
        "links": _links_from_result(result),
        "status_code": getattr(result, "status_code", None),
    }


def main() -> int:
    args = _read_input()
    url = str(args.get("url") or args.get("link") or "").strip()
    if not url:
        print(json.dumps({"ok": False, "error": "url required"}, ensure_ascii=False))
        return 2
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    max_chars = int(args.get("max_chars") or os.environ.get("CRAWL4AI_MAX_CHARS") or 40000)
    max_chars = max(2000, min(max_chars, 120_000))
    wait_for = args.get("wait_for")
    wait_for = str(wait_for).strip() if wait_for else None

    try:
        result = asyncio.run(_crawl(url, wait_for=wait_for))
    except Exception as exc:
        print(
            json.dumps(
                {"ok": False, "error": "runtime_error", "url": url, "detail": str(exc)},
                ensure_ascii=False,
            )
        )
        return 1

    if not result.get("ok"):
        print(json.dumps(result, ensure_ascii=False))
        return 1

    md, truncated = _truncate(str(result.get("markdown") or ""), max_chars)
    result["markdown"] = md
    result["truncated"] = truncated
    result["chars"] = len(md)
    # Hint for the model
    result["summary"] = (
        f"Crawled {url}"
        + (f" — {result.get('title')}" if result.get("title") else "")
        + f" ({result['chars']} chars"
        + (", truncated)" if truncated else ")")
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
