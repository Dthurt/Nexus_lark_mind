#!/usr/bin/env python3
"""Optional WeKnora HTTP read-only search — no-op unless WEKNORA_BASE_URL is set.

CLI plugin auto-registered when present under plugins_volume/cli/.
Does not replace the local SQLite knowledge base.

Uses the same normalize/citation shape as src.core_kernel.plugin_runtime.weknora_client
(stdlib-only here so the CLI process stays dependency-light).
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List


def _normalize_results(data: Any, *, limit: int) -> List[Dict[str, Any]]:
    rows: List[Any] = []
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        for key in ("results", "data", "items", "hits", "documents", "chunks"):
            val = data.get(key)
            if isinstance(val, list):
                rows = val
                break
            if isinstance(val, dict):
                for key2 in ("results", "items", "hits"):
                    if isinstance(val.get(key2), list):
                        rows = val[key2]
                        break
            if rows:
                break
    out: List[Dict[str, Any]] = []
    for row in rows[:limit]:
        if not isinstance(row, dict):
            continue
        title = str(
            row.get("title")
            or row.get("name")
            or row.get("doc_title")
            or row.get("document_name")
            or "WeKnora hit"
        )
        snippet = str(
            row.get("snippet")
            or row.get("content")
            or row.get("text")
            or row.get("chunk")
            or row.get("summary")
            or ""
        )[:800]
        source_uri = str(
            row.get("source_uri")
            or row.get("uri")
            or row.get("url")
            or row.get("path")
            or row.get("file_path")
            or ""
        )
        score = row.get("score") or row.get("relevance") or row.get("rerank_score")
        try:
            score_f = float(score) if score is not None else None
        except (TypeError, ValueError):
            score_f = None
        doc_id = str(row.get("doc_id") or row.get("document_id") or row.get("id") or "")
        citation = f"**{title}**"
        if source_uri:
            citation += f" — `{source_uri}`"
        citation += " (WeKnora)"
        out.append(
            {
                "title": title,
                "snippet": snippet,
                "source_uri": source_uri,
                "score": score_f,
                "doc_id": doc_id,
                "citation": citation,
                "source": "weknora",
            }
        )
    return out


def _citations_md(results: List[Dict[str, Any]]) -> str:
    if not results:
        return ""
    lines = ["### WeKnora references"]
    for i, r in enumerate(results, 1):
        cite = r.get("citation") or r.get("title") or "hit"
        snip = (r.get("snippet") or "").replace("\n", " ").strip()
        if len(snip) > 140:
            snip = snip[:137] + "…"
        lines.append(f"{i}. {cite}" + (f" — {snip}" if snip else ""))
    return "\n".join(lines)


def _http_json(url: str, headers: Dict[str, str], method: str = "GET", body: bytes | None = None) -> Any:
    req = urllib.request.Request(url, headers=headers, method=method, data=body)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def main() -> int:
    raw = sys.stdin.read() or "{}"
    try:
        args = json.loads(raw)
    except json.JSONDecodeError:
        args = {}
    query = str(args.get("query") or "").strip()
    limit = max(1, min(int(args.get("limit") or 5), 20))
    base = (os.getenv("WEKNORA_BASE_URL") or "").strip().rstrip("/")
    api_key = (os.getenv("WEKNORA_API_KEY") or "").strip()
    kb = str(args.get("kb_id") or os.getenv("WEKNORA_KB_ID") or "").strip()
    if not base:
        print(
            json.dumps(
                {
                    "ok": True,
                    "skipped": True,
                    "reason": "WEKNORA_BASE_URL not set — local KB remains default",
                    "results": [],
                    "citations_md": "",
                }
            )
        )
        return 0
    if not query:
        print(json.dumps({"ok": False, "error": "query required", "results": [], "citations_md": ""}))
        return 1

    path = (os.getenv("WEKNORA_SEARCH_PATH") or "/api/v1/search").strip()
    if not path.startswith("/"):
        path = "/" + path
    params = {"q": query, "query": query, "limit": limit}
    if kb:
        params["kb_id"] = kb
        params["knowledge_base_id"] = kb
    url = f"{base}{path}?{urllib.parse.urlencode(params)}"
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        try:
            data = _http_json(url, headers, method="GET")
        except urllib.error.HTTPError as exc:
            if exc.code not in (404, 405, 501):
                raise
            body_obj: Dict[str, Any] = {"query": query, "q": query, "limit": limit}
            if kb:
                body_obj["kb_id"] = kb
                body_obj["knowledge_base_id"] = kb
            post_url = f"{base}{path}"
            data = _http_json(
                post_url,
                headers,
                method="POST",
                body=json.dumps(body_obj).encode("utf-8"),
            )
        results = _normalize_results(data, limit=limit)
        print(
            json.dumps(
                {
                    "ok": True,
                    "source": "weknora",
                    "query": query,
                    "results": results,
                    "citations_md": _citations_md(results),
                },
                ensure_ascii=False,
            )
        )
        return 0
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc), "results": [], "citations_md": ""}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
