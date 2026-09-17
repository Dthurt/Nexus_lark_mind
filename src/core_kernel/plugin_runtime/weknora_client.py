"""WeKnora HTTP client — search, multi-KB, write, sync, and health.

Local SQLite remains NLM's default KB. WeKnora is an optional remote layer.

Env:
  WEKNORA_BASE_URL      — e.g. http://127.0.0.1:8080
  WEKNORA_API_KEY        — X-API-Key and/or Bearer
  WEKNORA_SEARCH_PATH    — override search path (default tries WeKnora native first)
  WEKNORA_KB_ID          — default knowledge-base id
  WEKNORA_INGEST_ENABLED — set 0 to disable write/sync push (read-only)
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

_API_PREFIX = "/api/v1"


def weknora_configured() -> bool:
    return bool((os.getenv("WEKNORA_BASE_URL") or "").strip())


def weknora_base_url() -> str:
    return (os.getenv("WEKNORA_BASE_URL") or "").strip().rstrip("/")


def weknora_default_kb_id() -> str:
    return (os.getenv("WEKNORA_KB_ID") or "").strip()


def weknora_kb_map() -> Dict[str, str]:
    """Parse WEKNORA_KB_MAP for workspace→KB routing.

    Accepts JSON object ``{"ws-id":"kb-id"}`` or comma pairs ``ws=kb,ws2=kb2``.
    """
    raw = (os.getenv("WEKNORA_KB_MAP") or "").strip()
    if not raw:
        return {}
    if raw.startswith("{"):
        try:
            import json

            data = json.loads(raw)
            if isinstance(data, dict):
                return {
                    str(k).strip(): str(v).strip()
                    for k, v in data.items()
                    if str(k).strip() and str(v).strip()
                }
        except Exception:
            return {}
    out: Dict[str, str] = {}
    for part in raw.split(","):
        part = part.strip()
        if not part or "=" not in part:
            continue
        k, _, v = part.partition("=")
        k, v = k.strip(), v.strip()
        if k and v:
            out[k] = v
    return out


def resolve_weknora_kb_id(
    *,
    kb_id: str = "",
    workspace_id: str = "",
    session_kb_id: str = "",
) -> str:
    """Resolve target KB: explicit → session → workspace map → global default."""
    for candidate in (kb_id, session_kb_id):
        val = (candidate or "").strip()
        if val:
            return val
    ws = (workspace_id or "").strip()
    if ws:
        mapped = weknora_kb_map().get(ws)
        if mapped:
            return mapped
    return weknora_default_kb_id()


def weknora_ingest_enabled() -> bool:
    raw = (os.getenv("WEKNORA_INGEST_ENABLED") or "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def weknora_search_path() -> str:
    path = (os.getenv("WEKNORA_SEARCH_PATH") or "").strip()
    if not path:
        return ""
    if not path.startswith("/"):
        path = "/" + path
    return path


def _auth_headers() -> Dict[str, str]:
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    api_key = (os.getenv("WEKNORA_API_KEY") or "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
        headers["X-API-Key"] = api_key
    return headers


def _not_configured(extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "ok": True,
        "skipped": True,
        "reason": "WEKNORA_BASE_URL not set — local KB remains default",
    }
    if extra:
        out.update(extra)
    return out


async def weknora_health() -> Dict[str, Any]:
    """Probe WeKnora online status + latency. Never raises."""
    base = weknora_base_url()
    if not base:
        return _not_configured({"online": False, "latency_ms": None})

    headers = _auth_headers()
    candidates = [
        f"{base}{_API_PREFIX}/knowledge-bases",
        f"{base}{_API_PREFIX}/system/info",
        f"{base}/health",
        f"{base}/api/health",
    ]
    t0 = time.perf_counter()
    last_error = ""
    async with httpx.AsyncClient(timeout=8.0) as client:
        for url in candidates:
            try:
                resp = await client.get(url, headers=headers)
                latency = round((time.perf_counter() - t0) * 1000, 1)
                if resp.status_code < 500:
                    kb_count: Optional[int] = None
                    if "knowledge-bases" in url and resp.status_code < 400:
                        data = _safe_json(resp)
                        rows = _extract_list(data)
                        kb_count = len(rows)
                    return {
                        "ok": True,
                        "online": resp.status_code < 400,
                        "status_code": resp.status_code,
                        "latency_ms": latency,
                        "kb_count": kb_count,
                        "probe": url.replace(base, ""),
                        "configured": True,
                        "default_kb_id": weknora_default_kb_id(),
                        "ingest_enabled": weknora_ingest_enabled(),
                    }
                last_error = f"HTTP {resp.status_code}"
            except Exception as exc:
                last_error = str(exc)
                continue
    return {
        "ok": False,
        "online": False,
        "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
        "error": last_error or "unreachable",
        "configured": True,
        "default_kb_id": weknora_default_kb_id(),
        "ingest_enabled": weknora_ingest_enabled(),
    }


async def weknora_list_knowledge_bases(*, limit: int = 50) -> Dict[str, Any]:
    """List remote knowledge bases (id / name / counts when available)."""
    base = weknora_base_url()
    if not base:
        return _not_configured({"knowledge_bases": []})

    url = f"{base}{_API_PREFIX}/knowledge-bases"
    headers = _auth_headers()
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(url, headers=headers, params={"page": 1, "page_size": max(1, min(limit, 100))})
            if resp.status_code >= 400:
                return {
                    "ok": False,
                    "error": f"WeKnora HTTP {resp.status_code}: {(resp.text or '')[:300]}",
                    "knowledge_bases": [],
                }
            data = _safe_json(resp)
    except Exception as exc:
        logger.warning("WeKnora list KBs failed: %s", exc)
        return {"ok": False, "error": str(exc), "knowledge_bases": []}

    rows = _extract_list(data)
    out: List[Dict[str, Any]] = []
    for row in rows[:limit]:
        if not isinstance(row, dict):
            continue
        kid = str(row.get("id") or row.get("kb_id") or row.get("knowledge_base_id") or "")
        if not kid:
            continue
        out.append(
            {
                "id": kid,
                "name": str(row.get("name") or row.get("title") or kid),
                "description": str(row.get("description") or row.get("desc") or "")[:400],
                "doc_count": _as_int(
                    row.get("doc_count")
                    or row.get("knowledge_count")
                    or row.get("document_count")
                    or row.get("total")
                ),
                "updated_at": str(row.get("updated_at") or row.get("updatedAt") or ""),
                "raw": {k: row[k] for k in list(row.keys())[:12]},
            }
        )
    return {
        "ok": True,
        "source": "weknora",
        "knowledge_bases": out,
        "default_kb_id": weknora_default_kb_id(),
        "count": len(out),
    }


async def weknora_search(
    query: str,
    *,
    limit: int = 5,
    kb_id: str = "",
    kb_ids: Optional[List[str]] = None,
    workspace_id: str = "",
    session_kb_id: str = "",
) -> Dict[str, Any]:
    """Search remote WeKnora. Never raises — returns ok/skipped/error envelopes."""
    q = (query or "").strip()
    base = weknora_base_url()
    if not base:
        return {
            **_not_configured(),
            "results": [],
            "citations_md": "",
        }
    if not q:
        return {"ok": False, "error": "query required", "results": [], "citations_md": ""}

    headers = _auth_headers()
    kb = resolve_weknora_kb_id(
        kb_id=kb_id, workspace_id=workspace_id, session_kb_id=session_kb_id
    ).strip()
    ids: List[str] = []
    if kb_ids:
        ids = [str(x).strip() for x in kb_ids if str(x).strip()]
    elif kb:
        ids = [kb]

    # 1) Preferred native WeKnora knowledge-search
    native = await _search_native(base, headers, q, limit=limit, kb_ids=ids)
    if native is not None:
        return native

    # 2) Legacy / custom path override
    custom_path = weknora_search_path()
    if custom_path:
        legacy = await _search_legacy(base, headers, custom_path, q, limit=limit, kb=kb)
        if legacy is not None:
            return legacy

    # 3) Final fallback: /api/v1/search
    return await _search_legacy(base, headers, f"{_API_PREFIX}/search", q, limit=limit, kb=kb) or {
        "ok": False,
        "error": "WeKnora search failed on all endpoints",
        "results": [],
        "citations_md": "",
        "source": "weknora",
    }


async def weknora_push_document(
    *,
    title: str,
    content: str,
    kb_id: str = "",
    workspace_id: str = "",
    session_kb_id: str = "",
    tag_id: str = "",
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Push Markdown/text into a WeKnora KB (manual knowledge)."""
    base = weknora_base_url()
    if not base:
        return _not_configured({"pushed": False})
    if not weknora_ingest_enabled():
        return {
            "ok": False,
            "error": "WeKnora ingest disabled (WEKNORA_INGEST_ENABLED=0)",
            "pushed": False,
        }
    kid = resolve_weknora_kb_id(
        kb_id=kb_id, workspace_id=workspace_id, session_kb_id=session_kb_id
    ).strip()
    if not kid:
        return {
            "ok": False,
            "error": "kb_id required (pass kb_id or set WEKNORA_KB_ID / WEKNORA_KB_MAP)",
            "pushed": False,
        }
    title_s = (title or "").strip() or "untitled"
    body = (content or "").strip()
    if not body:
        return {"ok": False, "error": "content required", "pushed": False}

    url = f"{base}{_API_PREFIX}/knowledge-bases/{kid}/knowledge/manual"
    payload: Dict[str, Any] = {"title": title_s, "content": body}
    if tag_id:
        payload["tag_id"] = tag_id
    if metadata:
        payload["metadata"] = metadata

    headers = _auth_headers()
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code >= 400:
                return {
                    "ok": False,
                    "error": f"WeKnora HTTP {resp.status_code}: {(resp.text or '')[:400]}",
                    "pushed": False,
                    "kb_id": kid,
                }
            data = _safe_json(resp)
    except Exception as exc:
        logger.warning("WeKnora push failed: %s", exc)
        return {"ok": False, "error": str(exc), "pushed": False, "kb_id": kid}

    knowledge_id = ""
    if isinstance(data, dict):
        nested = data.get("data") if isinstance(data.get("data"), dict) else data
        if isinstance(nested, dict):
            knowledge_id = str(
                nested.get("id")
                or nested.get("knowledge_id")
                or nested.get("document_id")
                or ""
            )
    return {
        "ok": True,
        "pushed": True,
        "source": "weknora",
        "kb_id": kid,
        "knowledge_id": knowledge_id,
        "title": title_s,
        "raw_keys": list(data.keys()) if isinstance(data, dict) else [],
    }


async def weknora_list_knowledge(
    kb_id: str = "",
    *,
    page: int = 1,
    page_size: int = 50,
) -> Dict[str, Any]:
    """List knowledge entries in a remote KB (for pull-sync)."""
    base = weknora_base_url()
    if not base:
        return _not_configured({"items": []})
    kid = (kb_id or weknora_default_kb_id()).strip()
    if not kid:
        return {"ok": False, "error": "kb_id required", "items": []}

    url = f"{base}{_API_PREFIX}/knowledge-bases/{kid}/knowledge"
    headers = _auth_headers()
    params = {"page": max(1, page), "page_size": max(1, min(page_size, 100))}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, headers=headers, params=params)
            if resp.status_code >= 400:
                return {
                    "ok": False,
                    "error": f"WeKnora HTTP {resp.status_code}: {(resp.text or '')[:300]}",
                    "items": [],
                    "kb_id": kid,
                }
            data = _safe_json(resp)
    except Exception as exc:
        return {"ok": False, "error": str(exc), "items": [], "kb_id": kid}

    rows = _extract_list(data)
    items: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        kid_doc = str(row.get("id") or row.get("knowledge_id") or "")
        items.append(
            {
                "id": kid_doc,
                "title": str(row.get("title") or row.get("file_name") or row.get("name") or kid_doc),
                "content": str(
                    row.get("content")
                    or row.get("markdown")
                    or row.get("text")
                    or row.get("description")
                    or ""
                ),
                "parse_status": str(row.get("parse_status") or ""),
                "updated_at": str(row.get("updated_at") or ""),
                "source_type": str(row.get("type") or row.get("source") or ""),
            }
        )
    return {"ok": True, "kb_id": kid, "items": items, "count": len(items)}


async def weknora_get_knowledge(knowledge_id: str) -> Dict[str, Any]:
    """Fetch a single knowledge entry (for content when list omits body)."""
    base = weknora_base_url()
    if not base:
        return _not_configured()
    kid = (knowledge_id or "").strip()
    if not kid:
        return {"ok": False, "error": "knowledge_id required"}
    url = f"{base}{_API_PREFIX}/knowledge/{kid}"
    headers = _auth_headers()
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code >= 400:
                return {
                    "ok": False,
                    "error": f"WeKnora HTTP {resp.status_code}: {(resp.text or '')[:300]}",
                }
            data = _safe_json(resp)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    row = data.get("data") if isinstance(data, dict) and isinstance(data.get("data"), dict) else data
    if not isinstance(row, dict):
        return {"ok": False, "error": "unexpected response shape"}
    return {
        "ok": True,
        "id": str(row.get("id") or kid),
        "title": str(row.get("title") or row.get("file_name") or kid),
        "content": str(row.get("content") or row.get("markdown") or row.get("text") or ""),
        "raw": row,
    }


# ----- internals -----


async def _search_native(
    base: str,
    headers: Dict[str, str],
    query: str,
    *,
    limit: int,
    kb_ids: List[str],
) -> Optional[Dict[str, Any]]:
    url = f"{base}{_API_PREFIX}/knowledge-search"
    body: Dict[str, Any] = {"query": query}
    if len(kb_ids) == 1:
        body["knowledge_base_id"] = kb_ids[0]
    elif len(kb_ids) > 1:
        body["knowledge_base_ids"] = kb_ids
    # WeKnora requires at least one KB id for knowledge-search
    if not kb_ids:
        listed = await weknora_list_knowledge_bases(limit=5)
        if listed.get("ok") and listed.get("knowledge_bases"):
            first = listed["knowledge_bases"][0]["id"]
            body["knowledge_base_id"] = first
            kb_ids = [first]
        else:
            return None
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=headers, json=body)
            if resp.status_code in (404, 405, 501):
                return None
            if resp.status_code >= 400:
                return {
                    "ok": False,
                    "error": f"WeKnora HTTP {resp.status_code}: {(resp.text or '')[:300]}",
                    "results": [],
                    "citations_md": "",
                    "source": "weknora",
                    "endpoint": "/api/v1/knowledge-search",
                }
            data = _safe_json(resp)
    except Exception as exc:
        logger.debug("WeKnora native search failed: %s", exc)
        return None

    results = _normalize_results(data, limit=limit)
    return {
        "ok": True,
        "source": "weknora",
        "endpoint": "/api/v1/knowledge-search",
        "query": query,
        "kb_ids": kb_ids,
        "results": results,
        "citations_md": _citations_md(results),
    }


async def _search_legacy(
    base: str,
    headers: Dict[str, str],
    path: str,
    query: str,
    *,
    limit: int,
    kb: str,
) -> Optional[Dict[str, Any]]:
    url = f"{base}{path}"
    params: Dict[str, Any] = {"q": query, "query": query, "limit": max(1, min(int(limit), 20))}
    if kb:
        params["kb_id"] = kb
        params["knowledge_base_id"] = kb
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, headers=headers, params=params)
            if resp.status_code in (404, 405, 501):
                body = {"query": query, "q": query, "limit": params["limit"]}
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
                    "endpoint": path,
                }
            data = _safe_json(resp)
    except Exception as exc:
        logger.warning("WeKnora legacy search failed (%s): %s", path, exc)
        return {
            "ok": False,
            "error": str(exc),
            "results": [],
            "citations_md": "",
            "source": "weknora",
            "endpoint": path,
        }

    results = _normalize_results(data, limit=int(params["limit"]))
    return {
        "ok": True,
        "source": "weknora",
        "endpoint": path,
        "query": query,
        "results": results,
        "citations_md": _citations_md(results),
        "raw_keys": list(data.keys()) if isinstance(data, dict) else [],
    }


def _safe_json(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except Exception:
        return {}


def _extract_list(data: Any) -> List[Any]:
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    for key in ("data", "items", "results", "knowledge_bases", "list", "rows"):
        val = data.get(key)
        if isinstance(val, list):
            return val
        if isinstance(val, dict):
            for key2 in ("items", "list", "results", "data", "knowledge_bases"):
                if isinstance(val.get(key2), list):
                    return val[key2]
    return []


def _as_int(value: Any) -> Optional[int]:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


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
            or row.get("knowledge_title")
            or row.get("knowledge_filename")
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
            or row.get("knowledge_filename")
            or ""
        )
        score = row.get("score") or row.get("relevance") or row.get("rerank_score")
        try:
            score_f = float(score) if score is not None else None
        except (TypeError, ValueError):
            score_f = None
        doc_id = str(
            row.get("doc_id")
            or row.get("document_id")
            or row.get("knowledge_id")
            or row.get("id")
            or ""
        )
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
                "kb_id": str(row.get("knowledge_base_id") or row.get("kb_id") or ""),
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
