"""Cheap local query expansion for KB recall (WeKnora-inspired, no LLM).

Used only when the first keyword/hybrid pass returns few hits.
Disable with KB_QUERY_EXPAND=0.
"""

from __future__ import annotations

import os
import re
from typing import Iterable, List, Sequence

_STOPWORDS = {
    "的",
    "是",
    "在",
    "了",
    "和",
    "与",
    "或",
    "a",
    "an",
    "the",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "have",
    "has",
    "had",
    "do",
    "does",
    "did",
    "will",
    "would",
    "could",
    "should",
    "may",
    "might",
    "must",
    "can",
    "to",
    "of",
    "in",
    "for",
    "on",
    "with",
    "at",
    "by",
    "from",
    "as",
    "into",
    "through",
    "about",
    "what",
    "how",
    "why",
    "when",
    "where",
    "which",
    "who",
    "whom",
    "whose",
}

_QUESTION_PREFIX = re.compile(
    r"^(什么是|什么|如何|怎么|怎样|为什么|为何|哪个|哪些|谁|何时|何地|"
    r"请问|请告诉我|帮我|我想知道|我想了解|what is|how to|how do|why )"
)

_PHRASE_RE = re.compile(r"[\"'「『]([^\"'」』]{2,80})[\"'」』]")
_SPLIT_RE = re.compile(r"[,，;；、。！？!?\s]+")
_TOKEN_RE = re.compile(
    r"[A-Za-z0-9_]+|[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]+"
)


def query_expand_enabled() -> bool:
    v = (os.getenv("KB_QUERY_EXPAND") or "1").strip().lower()
    return v not in {"0", "false", "no", "off"}


def _tokenize(text: str) -> List[str]:
    out: List[str] = []
    for m in _TOKEN_RE.finditer(text or ""):
        piece = m.group(0)
        if re.fullmatch(r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]+", piece):
            if len(piece) <= 4:
                out.append(piece)
            for i in range(len(piece) - 1):
                out.append(piece[i : i + 2])
        else:
            out.append(piece)
    return out


def extract_keywords(text: str) -> List[str]:
    words: List[str] = []
    seen: set[str] = set()
    for raw in _TOKEN_RE.findall(text or ""):
        w = raw.strip()
        if not w or w.lower() in _STOPWORDS:
            continue
        if len(w) < 2:
            continue
        key = w.lower()
        if key in seen:
            continue
        seen.add(key)
        words.append(w)
    return words


def expand_queries(query: str, *, limit: int = 5) -> List[str]:
    """Return local variants (not including the original)."""
    q = (query or "").strip()
    if not q:
        return []
    seen = {q.lower()}
    expansions: List[str] = []

    def add(s: str) -> None:
        s = (s or "").strip()
        if len(s) < 2:
            return
        key = s.lower()
        if key in seen:
            return
        seen.add(key)
        expansions.append(s)

    keywords = extract_keywords(q)
    if len(keywords) >= 2:
        add(" ".join(keywords))

    for phrase in _PHRASE_RE.findall(q):
        add(phrase)

    for seg in _SPLIT_RE.split(q):
        if len(seg.strip()) > 5:
            add(seg.strip())

    cleaned = _QUESTION_PREFIX.sub("", q).strip()
    if cleaned != q:
        add(cleaned)

    # Longest CJK / latin run as a focused probe
    runs = [m.group(0) for m in _TOKEN_RE.finditer(q)]
    if runs:
        longest = max(runs, key=len)
        if len(longest) >= 2:
            add(longest)

    return expansions[: max(1, limit)]


def should_expand(hit_count: int, limit: int) -> bool:
    if not query_expand_enabled():
        return False
    return hit_count < max(2, int(limit or 8) // 2)


def merge_hits_by_id(
    primary: Sequence[dict], extra: Iterable[dict], *, limit: int
) -> List[dict]:
    by_id: dict[str, dict] = {}
    order: List[str] = []

    def key_of(hit: dict) -> str:
        return str(hit.get("chunk_id") or hit.get("doc_id") or id(hit))

    for hit in list(primary) + list(extra):
        if not isinstance(hit, dict):
            continue
        key = key_of(hit)
        prev = by_id.get(key)
        if prev is None:
            by_id[key] = hit
            order.append(key)
            continue
        if float(hit.get("score") or 0) > float(prev.get("score") or 0):
            by_id[key] = hit
    ranked = sorted(
        (by_id[k] for k in order),
        key=lambda h: float(h.get("score") or 0),
        reverse=True,
    )
    return ranked[: max(1, limit)]
