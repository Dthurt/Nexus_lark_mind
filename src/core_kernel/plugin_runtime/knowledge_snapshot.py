"""Locate a search hit inside original chunk/doc text (retrieval snapshot, not RAG)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

DEFAULT_SNAPSHOT_RADIUS = 160


def locate_text_match(
    content: str,
    query: str = "",
    tokens: Optional[Sequence[str]] = None,
) -> Optional[Tuple[int, int, str]]:
    """Return (start, end, matched_text) for the first query/token hit, or None."""
    text = content or ""
    if not text:
        return None
    candidates: List[str] = []
    for t in tokens or []:
        s = str(t or "").strip()
        if s and s not in candidates:
            candidates.append(s)
    q = (query or "").strip()
    if q and q not in candidates:
        candidates.append(q)
    lower = text.lower()
    best: Optional[Tuple[int, int, str]] = None
    for c in candidates:
        i = lower.find(c.lower())
        if i < 0:
            continue
        hit = text[i : i + len(c)]
        if best is None or i < best[0] or (i == best[0] and len(c) > (best[1] - best[0])):
            best = (i, i + len(c), hit)
    return best


def build_text_snapshot(
    content: str,
    *,
    query: str = "",
    tokens: Optional[Sequence[str]] = None,
    radius: int = DEFAULT_SNAPSHOT_RADIUS,
) -> Dict[str, Any]:
    """Snippet plus surrounding context for “原文在这里” comparison."""
    text = content or ""
    loc = locate_text_match(text, query, tokens)
    if loc is None:
        snippet = (text[: radius * 2] + "…") if len(text) > radius * 2 else text
        preview = text[: min(len(text), radius * 2)]
        return {
            "snippet": snippet,
            "prefix": preview,
            "highlight": "",
            "suffix": "…" if len(text) > radius * 2 else "",
            "match_start": -1,
            "match_end": -1,
            "match_text": "",
            "match_kind": "semantic" if (query or "").strip() else "none",
        }
    start, end, hit = loc
    left = max(0, start - radius)
    right = min(len(text), end + radius)
    prefix = text[left:start]
    suffix = text[end:right]
    if left > 0:
        prefix = "…" + prefix
    if right < len(text):
        suffix = suffix + "…"
    return {
        "snippet": prefix + hit + suffix,
        "prefix": prefix,
        "highlight": hit,
        "suffix": suffix,
        "match_start": start,
        "match_end": end,
        "match_text": hit,
        "match_kind": "keyword",
    }
