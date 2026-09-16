"""Optional WeKnora HTTP client — read-only remote search with graceful degrade.

Local SQLite remains NLM's default KB. Set:
  WEKNORA_BASE_URL   — e.g. http://127.0.0.1:8080
  WEKNORA_API_KEY    — optional bearer
  WEKNORA_SEARCH_PATH — default /api/v1/search (override per deploy)
  WEKNORA_KB_ID      — optional knowledge-base id query param
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

import httpx

logger = logging.getLogger(__name__)


def weknora_configured() -> bool:
    return bool((os.getenv("WEKNORA_BASE_URL") or "").strip())


def weknora_base_url() -> str:
    return (os.getenv("WEKNORA_BASE_URL") or "").strip().rstrip("/")


def weknora_search_path() -> str:
    path = (os.getenv("WEKNORA_SEARCH_PATH") or "/api/v1/search").strip()
    if not path.startswith("/"):
        path = "/" + path
    return path


async def weknora_search(
    query: str,
    *,
    limit: int = 5,
    kb_id: str = "",
) -> Dict[str, Any]:
    """Search remote WeKnora. Never raises — returns ok/skipped/error envelopes."""
    q = (query or "").strip()
    base = weknora_base_url()
    if not base:
        return {
            "ok": True,
            "skipped": True,
            "reason": "WEKNORA_BASE_URL not set — local KB remains default",
            "results": [],
            "citations_md": "",
        }
    if not q:
        return {"ok": False, "error": "query required", "results": [], "citations_md": ""}

    api_key = (os.getenv("WEKNORA_API_KEY") or "").strip()
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    kb = (kb_id or os.getenv("WEKNORA_KB_ID") or "").strip()
    path = weknora_search_path()
    url = f"{base}{path}"
    params: Dict[str, Any] = {"q": q, "query": q, "limit": max(1, min(int(limit), 20))}
    if kb:
        params["kb_id"] = kb
        params["knowledge_base_id"] = kb

    # Try GET first (many gateways); on 404/405 fall back to POST JSON body.
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, headers=headers, params=params)
            if resp.status_code in (404, 405, 501):
                body = {"query": q, "q": q, "limit": params["limit"]}
                if kb:
                    body["kb_id"] = kb
                    body["knowledge_base_id"] = kb
                resp = await client.post(url, headers=headers, json=body)
            if resp.status_code >= 400:
                return {
                    "ok": False,
                    "error": f"WeKnora HTTP {resp.status_code}: {(resp.text or '')[:300]}",
                    "results": [],
                    "citations_md": "",
                    "source": "weknora",
                }
            data = resp.json()
    except Exception as exc:
        logger.warning("WeKnora search failed: %s", exc)
        return {
            "ok": False,
            "error": str(exc),
            "results": [],
            "citations_md": "",
            "source": "weknora",
        }

    results = _normalize_results(data, limit=int(params["limit"]))
    return {
        "ok": True,
        "source": "weknora",
        "query": q,
        "results": results,
        "citations_md": _citations_md(results),
        "raw_keys": list(data.keys()) if isinstance(data, dict) else [],
    }


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
