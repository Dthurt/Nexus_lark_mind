"""Optional second-stage KB rerank (WeKnora-inspired, local-first).

Default: cheap token-overlap rerank of the candidate pool (no extra service).
Optional HTTP: set KB_RERANK_URL to an OpenAI-style or Cohere-like endpoint.

  POST {KB_RERANK_URL}
  {"query": "...", "documents": ["...", ...]}  or  {"model": "...", "query": "...", "texts": [...]}

Disable entirely with KB_RERANK=0.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Sequence

import httpx


def rerank_enabled() -> bool:
    v = (os.getenv("KB_RERANK") or "1").strip().lower()
    return v not in {"0", "false", "no", "off"}


def rerank_url() -> str:
    return (os.getenv("KB_RERANK_URL") or "").strip().rstrip("/")


def _tokens(text: str) -> List[str]:
    import re

    return re.findall(r"[A-Za-z0-9_]{2,}|[\u4e00-\u9fff]{1,}", (text or "").lower())


def local_rerank_scores(query: str, documents: Sequence[str]) -> List[float]:
    """Overlap / length-normalized score in [0, 1]."""
    qset = set(_tokens(query))
    if not qset:
        return [0.0] * len(documents)
    out: List[float] = []
    for doc in documents:
        toks = _tokens(doc)
        if not toks:
            out.append(0.0)
            continue
        overlap = sum(1 for t in toks if t in qset)
        unique = len(set(toks) & qset)
        out.append(min(1.0, (overlap * 0.35 + unique * 1.4) / (4.0 + len(qset))))
    return out


async def http_rerank_scores(query: str, documents: Sequence[str]) -> List[float] | None:
    url = rerank_url()
    if not url or not documents:
        return None
    model = (os.getenv("KB_RERANK_MODEL") or "").strip()
    key = (os.getenv("KB_RERANK_API_KEY") or os.getenv("KB_EMBEDDING_API_KEY") or "").strip()
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    payload: Dict[str, Any] = {"query": query, "documents": list(documents)}
    if model:
        payload["model"] = model
        payload["texts"] = list(documents)
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        return None
    # Accept {results:[{index, score}]} or {scores:[...]} or list of floats
    if isinstance(data, list) and data and isinstance(data[0], (int, float)):
        return [float(x) for x in data[: len(documents)]]
    if isinstance(data, dict):
        if isinstance(data.get("scores"), list):
            return [float(x) for x in data["scores"][: len(documents)]]
        results = data.get("results") or data.get("data") or []
        scores = [0.0] * len(documents)
        if isinstance(results, list):
            for item in results:
                if not isinstance(item, dict):
                    continue
                try:
                    idx = int(item.get("index", -1))
                    sc = float(item.get("score") or item.get("relevance_score") or 0)
                except (TypeError, ValueError):
                    continue
                if 0 <= idx < len(scores):
                    scores[idx] = sc
            return scores
    return None


async def rerank_hits(query: str, hits: List[Dict[str, Any]], *, keep: int) -> List[Dict[str, Any]]:
    if not rerank_enabled() or len(hits) <= 1:
        return hits[:keep]
    docs = [
        " ".join(
            str(h.get(k) or "")
            for k in ("title", "heading", "context_header", "snippet", "citation")
        )
        for h in hits
    ]
    local = local_rerank_scores(query, docs)
    remote = await http_rerank_scores(query, docs)
    scored: List[tuple[float, Dict[str, Any]]] = []
    for i, hit in enumerate(hits):
        base = float(hit.get("score") or 0)
        loc = local[i] if i < len(local) else 0.0
        rem = remote[i] if remote and i < len(remote) else 0.0
        total = base * 0.35 + loc * 8.0 + rem * 12.0
        item = dict(hit)
        item["score"] = round(total, 3)
        item["rerank"] = round(loc if not rem else rem, 3)
        scored.append((total, item))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [h for _, h in scored[:keep]]
