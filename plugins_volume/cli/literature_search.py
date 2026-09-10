#!/usr/bin/env python3
"""Literature / paper search (simplified) via OpenAlex + optional Semantic Scholar.

Input (stdin JSON):
  {"query": "...", "max_results": 5, "year_from": 2018}

Output:
  {"ok": true, "provider": "openalex", "query": "...", "results":[
     {"title","authors","year","url","doi","abstract","venue"}
  ], "references_md": "..."}
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List


def _read_input() -> Dict[str, Any]:
    raw = sys.stdin.read().strip() or "{}"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {"query": raw}
    return data if isinstance(data, dict) else {"query": str(data)}


def _http_json(url: str, headers: Dict[str, str] | None = None) -> Any:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Nexus-Lark-Mind/1.0 (mailto:research@local)", **(headers or {})},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=40) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _authors(authorships: List[Dict[str, Any]]) -> str:
    names = []
    for a in authorships or []:
        author = a.get("author") or {}
        name = author.get("display_name") or ""
        if name:
            names.append(name)
    return ", ".join(names[:8]) + (" et al." if len(names) > 8 else "")


def search_openalex(query: str, max_results: int, year_from: int | None) -> Dict[str, Any]:
    params: Dict[str, Any] = {
        "search": query,
        "per_page": max_results,
        "sort": "relevance_score:desc",
    }
    if year_from:
        params["filter"] = f"from_publication_date:{year_from}-01-01"
    url = "https://api.openalex.org/works?" + urllib.parse.urlencode(params)
    data = _http_json(url)
    rows = []
    for w in data.get("results") or []:
        doi = (w.get("doi") or "").replace("https://doi.org/", "")
        landing = ""
        primary = w.get("primary_location") or {}
        landing = primary.get("landing_page_url") or ""
        if not landing and doi:
            landing = f"https://doi.org/{doi}"
        ids = w.get("ids") or {}
        oa = ids.get("openalex") or w.get("id") or ""
        if not landing and oa:
            landing = oa
        abstract = ""
        inv = w.get("abstract_inverted_index") or {}
        if inv:
            # Reconstruct rough abstract from inverted index
            positions: Dict[int, str] = {}
            for word, idxs in inv.items():
                for i in idxs:
                    positions[int(i)] = word
            abstract = " ".join(positions[i] for i in sorted(positions)[:120])
        rows.append(
            {
                "title": w.get("display_name") or w.get("title") or "",
                "authors": _authors(w.get("authorships") or []),
                "year": (w.get("publication_year") or ""),
                "url": landing,
                "doi": doi,
                "venue": ((w.get("primary_location") or {}).get("source") or {}).get("display_name")
                or "",
                "cited_by": w.get("cited_by_count") or 0,
                "abstract": abstract,
            }
        )
    return {"ok": True, "provider": "openalex", "query": query, "results": rows}


def search_semantic_scholar(query: str, max_results: int) -> Dict[str, Any]:
    key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "").strip()
    headers = {"User-Agent": "Nexus-Lark-Mind/1.0"}
    if key:
        headers["x-api-key"] = key
    q = urllib.parse.urlencode(
        {
            "query": query,
            "limit": max_results,
            "fields": "title,authors,year,url,externalIds,abstract,venue,citationCount",
        }
    )
    data = _http_json(f"https://api.semanticscholar.org/graph/v1/paper/search?{q}", headers=headers)
    rows = []
    for p in data.get("data") or []:
        ext = p.get("externalIds") or {}
        doi = ext.get("DOI") or ""
        url = p.get("url") or (f"https://doi.org/{doi}" if doi else "")
        authors = ", ".join((a.get("name") or "") for a in (p.get("authors") or [])[:8])
        rows.append(
            {
                "title": p.get("title") or "",
                "authors": authors,
                "year": p.get("year") or "",
                "url": url,
                "doi": doi,
                "venue": p.get("venue") or "",
                "cited_by": p.get("citationCount") or 0,
                "abstract": (p.get("abstract") or "")[:600],
            }
        )
    return {"ok": True, "provider": "semantic_scholar", "query": query, "results": rows}


def format_references_md(results: List[Dict[str, Any]]) -> str:
    lines = ["## References"]
    for i, r in enumerate(results, 1):
        title = r.get("title") or "Untitled"
        authors = r.get("authors") or "Unknown"
        year = r.get("year") or "n.d."
        url = r.get("url") or ""
        doi = r.get("doi") or ""
        cite = f"{i}. {authors} ({year}). *{title}*."
        if doi:
            cite += f" DOI: {doi}."
        if url:
            cite += f" {url}"
        lines.append(cite)
    return "\n".join(lines)


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
    year_from = None
    try:
        if data.get("year_from"):
            year_from = int(data["year_from"])
    except (TypeError, ValueError):
        year_from = None

    errors: List[str] = []
    for name, fn in (
        ("openalex", lambda: search_openalex(query, max_results, year_from)),
        ("semantic_scholar", lambda: search_semantic_scholar(query, max_results)),
    ):
        try:
            result = fn()
            result["references_md"] = format_references_md(result.get("results") or [])
            print(json.dumps(result, ensure_ascii=False))
            return
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{name}: {exc}")

    print(
        json.dumps(
            {"ok": False, "error": "literature search failed", "detail": errors},
            ensure_ascii=False,
        )
    )
    sys.exit(1)


if __name__ == "__main__":
    main()
