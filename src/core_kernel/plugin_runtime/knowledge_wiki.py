"""Local second-layer Wiki distill: keep raw docs, write editable interlinked pages."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple
from uuid import uuid4

import httpx

from src.core_kernel.plugin_runtime.knowledge_scope import (
    is_remote_kb_id,
    normalize_local_kb_id,
)
from src.core_kernel.plugin_runtime.knowledge_store import KnowledgeStore, content_hash

logger = logging.getLogger(__name__)

WIKI_LINK_RE = re.compile(r"\[\[([^\[\]]+)\]\]")
INDEX_SLUG = "_index"


def wiki_enabled() -> bool:
    return (os.getenv("KB_WIKI") or "1").strip().lower() not in {"0", "false", "no", "off"}


def wiki_auto() -> bool:
    return (os.getenv("KB_WIKI_AUTO") or "").strip().lower() in {"1", "true", "yes", "on"}


def slugify(title: str) -> str:
    s = (title or "").strip().lower()
    if s.startswith("doc:"):
        s = s[4:]
    s = re.sub(r"[\[\]#?&=\s]+", "-", s)
    s = re.sub(r"[^a-z0-9\u4e00-\u9fff\-_.]+", "", s)
    s = re.sub(r"-{2,}", "-", s).strip("-._")
    return (s or "page")[:80]


def parse_wikilinks(content: str) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    seen: set[Tuple[str, str]] = set()
    for match in WIKI_LINK_RE.finditer(content or ""):
        raw = match.group(0)
        inner = match.group(1).strip()
        if "|" in inner:
            target, label = inner.split("|", 1)
            target, label = target.strip(), (label.strip() or target.strip())
        else:
            target, label = inner, inner
        if target.lower().startswith("doc:"):
            to_kind, to_id = "doc", target[4:].strip()
        else:
            to_kind, to_id = "page", slugify(target)
        key = (to_kind, to_id)
        if not to_id or key in seen:
            continue
        seen.add(key)
        out.append({"to_kind": to_kind, "to_id": to_id, "label": label, "raw": raw})
    return out


def _env(name: str) -> str:
    return (os.getenv(name) or "").strip()


def chat_configured() -> bool:
    return bool(_chat_config()[1])


def _chat_config() -> Tuple[str, str, str]:
    glm_key = _env("GLM_API_KEY")
    if glm_key:
        base = (_env("GLM_BASE_URL") or "https://open.bigmodel.cn/api/paas/v4").rstrip("/")
        model = _env("GLM_DEFAULT_MODEL") or _env("GLM_MODEL") or "glm-4-flash"
        return base, glm_key, model
    key = _env("OPENAI_API_KEY")
    if key:
        base = (_env("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        model = _env("OPENAI_DEFAULT_MODEL") or _env("OPENAI_MODEL") or "gpt-4o-mini"
        return base, key, model
    return "", "", ""


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    raw = (text or "").strip()
    if not raw:
        return None
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except Exception:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            try:
                data = json.loads(raw[start : end + 1])
                return data if isinstance(data, dict) else None
            except Exception:
                return None
    return None


def _outline_markdown(title: str, doc_id: str, content: str) -> str:
    headings: List[str] = []
    excerpt = ""
    for line in (content or "").splitlines():
        s = line.strip()
        if s.startswith("#"):
            headings.append(s)
        elif s and not excerpt and not s.startswith("```"):
            excerpt = s[:400]
        if len(headings) >= 16 and excerpt:
            break
    parts = [f"# {title}", ""]
    if excerpt:
        parts.extend([excerpt, ""])
    if headings:
        parts.append("## 提纲")
        parts.extend(f"- {h.lstrip('#').strip()}" for h in headings[:16])
        parts.append("")
    parts.append("## 来源")
    parts.append(f"- [[doc:{doc_id}|原文]]")
    return "\n".join(parts).strip() + "\n"


def rule_distill_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    title = str(doc.get("title") or doc.get("doc_id") or "untitled")
    doc_id = str(doc.get("doc_id") or "")
    slug = slugify(title)
    markdown = _outline_markdown(title, doc_id, str(doc.get("content") or ""))
    return {
        "title": title,
        "slug": slug,
        "markdown": markdown,
        "source_doc_ids": [doc_id] if doc_id else [],
        "entities": [{"label": title}],
        "triples": [{"src": title, "rel": "mentions", "dst": f"doc:{doc_id}"}] if doc_id else [],
    }


DISTILL_SYSTEM = """You distill source documents into a small interlinked wiki.
Return ONLY JSON:
{
  "pages": [{"title": "...", "slug": "kebab-or-cjk", "markdown": "...", "source_doc_ids": ["..."]}],
  "entities": [{"label": "..."}],
  "triples": [{"src": "Entity or Page", "rel": "related|mentions", "dst": "Entity or Page"}]
}
Rules:
- 2-6 pages for this batch
- Markdown only, no HTML
- Use [[OtherPage]] or [[slug|label]] wiki links
- Every page must cite sources as [[doc:DOC_ID|原文]]
- Prefer merging overlapping topics; do not invent facts
"""


async def _llm_json(user: str) -> Optional[Dict[str, Any]]:
    base, key, model = _chat_config()
    if not base or not key:
        return None
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": DISTILL_SYSTEM},
            {"role": "user", "content": user},
        ],
        "temperature": 0.2,
    }
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post(
                f"{base}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()
        text = (
            (((data.get("choices") or [{}])[0].get("message") or {}).get("content"))
            if isinstance(data, dict)
            else ""
        )
        return _extract_json(str(text or ""))
    except Exception:
        logger.warning("wiki llm distill failed", exc_info=True)
        return None


def _pack_docs(docs: Sequence[Dict[str, Any]], *, max_chars: int = 12000) -> str:
    parts: List[str] = []
    used = 0
    for doc in docs:
        body = str(doc.get("content") or "")
        if len(body) > 6000:
            body = body[:6000] + "\n…"
        block = (
            f"DOC_ID={doc.get('doc_id')}\nTITLE={doc.get('title')}\n---\n{body}\n"
        )
        if used + len(block) > max_chars and parts:
            break
        parts.append(block)
        used += len(block)
    return "\n\n".join(parts)


async def distill_docs(
    docs: Sequence[Dict[str, Any]], *, prefer_llm: bool = True
) -> Dict[str, Any]:
    pages: List[Dict[str, Any]] = []
    entities: List[Dict[str, Any]] = []
    triples: List[Dict[str, Any]] = []
    mode = "rules"
    pending = list(docs)
    if prefer_llm and pending and chat_configured():
        packed = pending[:4]
        data = await _llm_json(_pack_docs(packed))
        if data:
            mode = "llm"
            pages.extend(list(data.get("pages") or []))
            entities.extend(list(data.get("entities") or []))
            triples.extend(list(data.get("triples") or []))
            used = {str(d.get("doc_id") or "") for d in packed}
            pending = [d for d in pending if str(d.get("doc_id") or "") not in used]
        else:
            mode = "rules"
    for doc in pending:
        item = rule_distill_doc(doc)
        pages.append(
            {
                "title": item["title"],
                "slug": item["slug"],
                "markdown": item["markdown"],
                "source_doc_ids": item["source_doc_ids"],
            }
        )
        entities.extend(item["entities"])
        triples.extend(item["triples"])
    return {"mode": mode, "pages": pages, "entities": entities, "triples": triples}


async def enqueue_wiki_distill(
    store: KnowledgeStore,
    *,
    kb_id: str,
    workspace_id: str = "",
    doc_ids: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    from src.core_kernel.plugin_runtime.knowledge_jobs import kick_job

    if not wiki_enabled():
        raise ValueError("KB_WIKI is disabled")
    if is_remote_kb_id(kb_id):
        raise ValueError("Wiki distill is local-only")
    local_id = normalize_local_kb_id(kb_id)
    job_id = f"job_{uuid4().hex[:16]}"
    payload = {"doc_ids": [str(x) for x in doc_ids or [] if str(x).strip()]}
    job = await store.create_ingest_job(
        job_id=job_id,
        kind="wiki_distill",
        filename="wiki",
        source_uri=json.dumps(payload, ensure_ascii=False),
        kb_id=local_id,
        workspace_id=workspace_id,
        title="生成本库 Wiki",
        status="pending",
        progress=0,
        message="queued",
    )
    await kick_job(store, job_id)
    return (await store.get_ingest_job(job_id)) or job


async def maybe_auto_distill(
    store: KnowledgeStore,
    *,
    kb_id: str,
    workspace_id: str = "",
    doc_ids: Optional[Sequence[str]] = None,
) -> Optional[Dict[str, Any]]:
    if not wiki_enabled() or not wiki_auto():
        return None
    if is_remote_kb_id(kb_id):
        return None
    try:
        return await enqueue_wiki_distill(
            store, kb_id=kb_id, workspace_id=workspace_id, doc_ids=doc_ids
        )
    except Exception:
        logger.warning("auto wiki distill enqueue failed", exc_info=True)
        return None


def _unique_slug(base: str, taken: set[str]) -> str:
    slug = slugify(base)
    if slug not in taken:
        taken.add(slug)
        return slug
    i = 2
    while f"{slug}-{i}" in taken:
        i += 1
    out = f"{slug}-{i}"
    taken.add(out)
    return out


def _node_id_for_label(
    kb_id: str, label: str, *, pages_by_slug: Dict[str, Dict[str, Any]]
) -> str:
    raw = (label or "").strip()
    if raw.startswith("doc:"):
        return f"doc:{raw[4:]}"
    slug = slugify(raw)
    page = pages_by_slug.get(slug)
    if page:
        return f"page:{page['page_id']}"
    return f"ent:{kb_id}:{slug}"


async def _write_index_page(
    store: KnowledgeStore,
    *,
    kb_id: str,
    workspace_id: str,
    pages: Sequence[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    existing = await store.get_wiki_page(kb_id, INDEX_SLUG, include_revisions=True)
    if existing and await store.wiki_page_is_user_dirty(str(existing.get("page_id") or "")):
        return None
    lines = ["# 本库概述", "", "本页由蒸馏生成，列出本库 Wiki 页。", ""]
    for page in pages:
        slug = str(page.get("slug") or "")
        if not slug or slug == INDEX_SLUG:
            continue
        title = str(page.get("title") or slug)
        lines.append(f"- [[{slug}|{title}]]")
    return await store.save_wiki_page(
        kb_id=kb_id,
        slug=INDEX_SLUG,
        title="本库概述",
        content="\n".join(lines).strip() + "\n",
        author="agent",
        message="distill index",
        status="published",
        workspace_id=workspace_id,
    )


async def apply_distill(
    store: KnowledgeStore,
    *,
    kb_id: str,
    workspace_id: str,
    bundle: Dict[str, Any],
) -> Dict[str, Any]:
    local_id = normalize_local_kb_id(kb_id)
    written: List[Dict[str, Any]] = []
    conflicts: List[str] = []
    skipped: List[str] = []
    existing_rows = await store.list_wiki_pages(local_id, limit=500)
    taken = {str(p.get("slug") or "") for p in existing_rows}
    source_ids: List[str] = []
    for page in bundle.get("pages") or []:
        source_ids.extend(str(x) for x in (page.get("source_doc_ids") or []) if str(x).strip())
    source_ids = list(dict.fromkeys(source_ids))
    if source_ids:
        await store.delete_graph_for_sources(local_id, source_ids)

    pages_by_slug: Dict[str, Dict[str, Any]] = {}
    for raw in bundle.get("pages") or []:
        title = str(raw.get("title") or "untitled")
        wanted = slugify(str(raw.get("slug") or title))
        markdown = str(raw.get("markdown") or "")
        sources = [str(x) for x in (raw.get("source_doc_ids") or []) if str(x).strip()]
        current = await store.get_wiki_page(local_id, wanted, include_revisions=True)
        if current and await store.wiki_page_is_user_dirty(str(current.get("page_id") or "")):
            draft_slug = _unique_slug(f"{wanted}-draft", taken)
            saved = await store.save_wiki_page(
                kb_id=local_id,
                slug=draft_slug,
                title=f"{title}（待合并）",
                content=markdown,
                author="agent",
                message="待合并：用户已编辑原页",
                status="draft",
                source_doc_ids=sources,
                workspace_id=workspace_id,
            )
            conflicts.append(wanted)
            written.append(saved)
            pages_by_slug[draft_slug] = saved
            continue
        slug = wanted if current else _unique_slug(wanted, taken)
        saved = await store.save_wiki_page(
            kb_id=local_id,
            slug=slug,
            title=title,
            content=markdown,
            author="agent",
            message="wiki distill",
            status="published",
            source_doc_ids=sources,
            workspace_id=workspace_id,
        )
        written.append(saved)
        pages_by_slug[slug] = saved

    all_pages = await store.list_wiki_pages(local_id, limit=500)
    index = await _write_index_page(
        store, kb_id=local_id, workspace_id=workspace_id, pages=all_pages
    )
    if index:
        written.append(index)
        pages_by_slug[INDEX_SLUG] = index
    else:
        skipped.append(INDEX_SLUG)

    for ent in bundle.get("entities") or []:
        label = str(ent.get("label") or "").strip()
        if not label:
            continue
        node_id = _node_id_for_label(local_id, label, pages_by_slug=pages_by_slug)
        if node_id.startswith("page:") or node_id.startswith("doc:"):
            continue
        src = source_ids[0] if source_ids else ""
        await store.upsert_graph_node(
            kb_id=local_id,
            node_id=node_id,
            kind="entity",
            label=label,
            source_doc_id=src,
        )

    for triple in bundle.get("triples") or []:
        src = str(triple.get("src") or "").strip()
        dst = str(triple.get("dst") or "").strip()
        rel = str(triple.get("rel") or "related")[:32]
        if not src or not dst:
            continue
        from_id = _node_id_for_label(local_id, src, pages_by_slug=pages_by_slug)
        to_id = _node_id_for_label(local_id, dst, pages_by_slug=pages_by_slug)
        if from_id.startswith("ent:"):
            await store.upsert_graph_node(
                kb_id=local_id,
                node_id=from_id,
                kind="entity",
                label=src,
                source_doc_id=source_ids[0] if source_ids else "",
            )
        if to_id.startswith("doc:"):
            await store.upsert_graph_node(
                kb_id=local_id,
                node_id=to_id,
                kind="doc",
                label=dst[4:] if dst.startswith("doc:") else dst,
                doc_id=to_id[4:],
                source_doc_id=to_id[4:],
            )
        elif to_id.startswith("ent:"):
            await store.upsert_graph_node(
                kb_id=local_id,
                node_id=to_id,
                kind="entity",
                label=dst,
                source_doc_id=source_ids[0] if source_ids else "",
            )
        await store.upsert_graph_edge(
            kb_id=local_id,
            from_id=from_id,
            to_id=to_id,
            rel=rel if rel in {"wiki_link", "mentions", "related"} else "related",
            source_doc_id=source_ids[0] if source_ids else "",
            evidence=f"{src} {rel} {dst}",
        )

    return {
        "pages": written,
        "conflicts": conflicts,
        "skipped": skipped,
        "mode": str(bundle.get("mode") or "rules"),
    }


async def process_wiki_distill(store: KnowledgeStore, job_id: str) -> Dict[str, Any]:
    job = await store.get_ingest_job(job_id)
    if not job:
        return {"job_id": job_id, "status": "failed", "error": "job not found"}
    if job.get("status") == "completed":
        return job
    kb_id = normalize_local_kb_id(str(job.get("kb_id") or ""))
    workspace_id = str(job.get("workspace_id") or "")
    await store.update_ingest_job(job_id, status="processing", progress=15, message="collecting docs")
    try:
        payload: Dict[str, Any] = {}
        try:
            loaded = json.loads(str(job.get("source_uri") or "{}"))
            if isinstance(loaded, dict):
                payload = loaded
        except Exception:
            payload = {}
        wanted = [str(x) for x in (payload.get("doc_ids") or []) if str(x).strip()]
        docs: List[Dict[str, Any]] = []
        if wanted:
            for doc_id in wanted:
                row = await store.get(doc_id)
                if row and str(row.get("source") or "") != "wiki":
                    docs.append(row)
        else:
            listed = await store.list_docs(workspace_id=workspace_id, kb_id=kb_id, limit=80)
            for item in listed:
                row = await store.get(str(item.get("doc_id") or ""))
                if row and str(row.get("source") or "") not in {"wiki", "session-upload"}:
                    docs.append(row)
        if not docs:
            updated = await store.update_ingest_job(
                job_id,
                status="completed",
                progress=100,
                message="no documents to distill",
                error="",
            )
            return {**updated, "pages": [], "conflicts": []}
        await store.update_ingest_job(job_id, progress=45, message="distilling")
        bundle = await distill_docs(docs, prefer_llm=True)
        await store.update_ingest_job(job_id, progress=75, message="writing wiki")
        result = await apply_distill(
            store, kb_id=kb_id, workspace_id=workspace_id, bundle=bundle
        )
        note = "llm distill" if result.get("mode") == "llm" else "规则蒸馏"
        if result.get("conflicts"):
            note += f"；{len(result['conflicts'])} 页用户已改，已写待合并草稿"
        updated = await store.update_ingest_job(
            job_id,
            status="completed",
            progress=100,
            message=note,
            error="",
        )
        return {
            **updated,
            "pages": [
                {"slug": p.get("slug"), "title": p.get("title"), "status": p.get("status")}
                for p in result.get("pages") or []
            ],
            "conflicts": result.get("conflicts") or [],
            "mode": result.get("mode"),
        }
    except Exception as exc:
        logger.exception("wiki distill %s crashed", job_id)
        return await store.update_ingest_job(
            job_id,
            status="failed",
            progress=100,
            message="failed",
            error=str(exc)[:2000],
        )
