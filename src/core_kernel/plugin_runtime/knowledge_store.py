"""Local SQLite knowledge base — chunked keyword + optional hybrid vector search."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from urllib.parse import quote
from typing import Any, Dict, List, Optional, Sequence, Tuple
from uuid import uuid4

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    delete,
    func,
    or_,
    select,
    text,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from src.core_kernel.plugin_runtime.knowledge_embeddings import (
    cosine_similarity,
    deserialize_embedding,
    effective_embedding_stats,
    embed_one,
    embed_one_image,
    embed_texts,
    embeddings_configured,
    resolve_embedding_endpoint,
    serialize_embedding,
    multimodal_embeddings_enabled,
)
from src.core_kernel.plugin_runtime.knowledge_scope import (
    DEFAULT_LOCAL_KB_ID,
    DEFAULT_LOCAL_KB_NAME,
    is_all_local_kbs,
    local_kb_match_values,
    normalize_local_kb_id,
)
from src.core_kernel.plugin_runtime.knowledge_snapshot import build_text_snapshot
from src.infrastructure.storage.database import Base

logger = logging.getLogger(__name__)

CHUNK_TARGET = 512
CHUNK_OVERLAP_RATIO = 0.15
CHILD_CHUNK_TARGET = 384
PARENT_CHUNK_TARGET = 2048
SNIPPET_RADIUS = 160
SHORT_CHUNK_EXPAND = 350


def row_visible_for_session(row: Optional[Dict[str, Any]], session_id: str = "") -> bool:
    """Session-upload docs are only visible to the owning session."""
    if not row:
        return False
    source = str(row.get("source") or "").strip()
    if source != "session-upload":
        return True
    sid = (session_id or "").strip()
    return bool(sid) and f"session:{sid}" in str(row.get("tags") or "")


class KnowledgeDoc(Base):
    __tablename__ = "knowledge_docs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doc_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(512), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[str] = mapped_column(String(512), default="")  # comma-separated
    source: Mapped[str] = mapped_column(String(256), default="")
    source_uri: Mapped[str] = mapped_column(String(1024), default="")
    content_hash: Mapped[str] = mapped_column(String(64), default="", index=True)
    workspace_id: Mapped[str] = mapped_column(String(128), default="", index=True)
    kb_id: Mapped[str] = mapped_column(String(80), default="", index=True)
    parse_status: Mapped[str] = mapped_column(String(32), default="completed")
    parse_error: Mapped[str] = mapped_column(String(1024), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chunk_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    doc_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("knowledge_docs.doc_id", ondelete="CASCADE"), index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    heading: Mapped[str] = mapped_column(String(512), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    char_start: Mapped[int] = mapped_column(Integer, default=0)
    char_end: Mapped[int] = mapped_column(Integer, default=0)
    embedding: Mapped[str] = mapped_column(Text, default="")  # JSON float array
    embedding_model: Mapped[str] = mapped_column(String(128), default="")
    parent_chunk_id: Mapped[str] = mapped_column(String(80), default="", index=True)
    chunk_type: Mapped[str] = mapped_column(String(32), default="text")  # text|parent|image
    context_header: Mapped[str] = mapped_column(String(1024), default="")
    workspace_id: Mapped[str] = mapped_column(String(128), default="", index=True)
    kb_id: Mapped[str] = mapped_column(String(80), default="", index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class KnowledgeSyncLog(Base):
    __tablename__ = "knowledge_sync_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(64), default="", index=True)
    source_uri: Mapped[str] = mapped_column(String(1024), default="")
    content_hash: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(32), default="ok")  # ok|skip|error
    message: Mapped[str] = mapped_column(Text, default="")
    workspace_id: Mapped[str] = mapped_column(String(128), default="", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kb_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(256), default="")
    description: Mapped[str] = mapped_column(String(1024), default="")
    workspace_id: Mapped[str] = mapped_column(String(128), default="", index=True)
    chunk_strategy: Mapped[str] = mapped_column(String(32), default="parent_child")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class KnowledgeIngestJob(Base):
    __tablename__ = "knowledge_ingest_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    kind: Mapped[str] = mapped_column(String(16), default="file")  # file|url|wiki_distill
    filename: Mapped[str] = mapped_column(String(512), default="")
    source_uri: Mapped[str] = mapped_column(String(2048), default="")
    title: Mapped[str] = mapped_column(String(512), default="")
    status: Mapped[str] = mapped_column(String(32), default="pending")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str] = mapped_column(String(512), default="")
    error: Mapped[str] = mapped_column(Text, default="")
    bytes_len: Mapped[int] = mapped_column(Integer, default=0)
    doc_id: Mapped[str] = mapped_column(String(64), default="")
    kb_id: Mapped[str] = mapped_column(String(80), default="", index=True)
    workspace_id: Mapped[str] = mapped_column(String(128), default="", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class KnowledgeWikiPage(Base):
    __tablename__ = "knowledge_wiki_pages"
    __table_args__ = (UniqueConstraint("kb_id", "slug", name="uq_wiki_page_kb_slug"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    page_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    kb_id: Mapped[str] = mapped_column(String(80), default="", index=True)
    slug: Mapped[str] = mapped_column(String(160), default="", index=True)
    title: Mapped[str] = mapped_column(String(512), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="published")
    source_doc_ids: Mapped[str] = mapped_column(Text, default="[]")
    content_hash: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class KnowledgeWikiRevision(Base):
    __tablename__ = "knowledge_wiki_revisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    revision_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    page_id: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(512), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    author: Mapped[str] = mapped_column(String(16), default="agent")  # user|agent
    message: Mapped[str] = mapped_column(String(512), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class KnowledgeWikiLink(Base):
    __tablename__ = "knowledge_wiki_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    from_page_id: Mapped[str] = mapped_column(String(64), index=True)
    to_kind: Mapped[str] = mapped_column(String(16), default="page")  # page|doc
    to_id: Mapped[str] = mapped_column(String(160), default="")
    label: Mapped[str] = mapped_column(String(256), default="")
    raw: Mapped[str] = mapped_column(String(512), default="")


class KnowledgeGraphNode(Base):
    __tablename__ = "knowledge_graph_nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    node_id: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    kb_id: Mapped[str] = mapped_column(String(80), default="", index=True)
    kind: Mapped[str] = mapped_column(String(16), default="entity")  # entity|page|doc
    label: Mapped[str] = mapped_column(String(512), default="")
    page_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    doc_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    source_doc_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    attrs: Mapped[str] = mapped_column(Text, default="{}")


class KnowledgeGraphEdge(Base):
    __tablename__ = "knowledge_graph_edges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    edge_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    kb_id: Mapped[str] = mapped_column(String(80), default="", index=True)
    from_id: Mapped[str] = mapped_column(String(120), default="", index=True)
    to_id: Mapped[str] = mapped_column(String(120), default="", index=True)
    rel: Mapped[str] = mapped_column(String(32), default="related")  # wiki_link|mentions|related
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    evidence: Mapped[str] = mapped_column(String(1024), default="")
    source_doc_id: Mapped[str] = mapped_column(String(64), default="", index=True)


def wiki_index_doc_id(page_id: str) -> str:
    return f"wiki:{page_id}"


def _json_list(raw: Any) -> List[str]:
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    if isinstance(raw, str) and raw.strip():
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                return [str(x).strip() for x in data if str(x).strip()]
        except Exception:
            return [raw.strip()] if raw.strip() else []
    return []


def content_hash(text_body: str) -> str:
    return hashlib.sha256((text_body or "").encode("utf-8")).hexdigest()


_CJK_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]+")


def _tokens(q: str) -> List[str]:
    """Keyword tokens + CJK character bigrams for better Chinese matching."""
    raw = (q or "").strip().lower()
    if not raw:
        return []
    parts = re.split(r"[\s,;|/]+", raw)
    out: List[str] = []
    seen: set[str] = set()

    def _add(t: str) -> None:
        t = t.strip()
        if len(t) < 2 or t in seen:
            return
        seen.add(t)
        out.append(t)

    for p in parts:
        if not p:
            continue
        _add(p)
        # Split mixed latin/CJK runs
        for m in re.finditer(r"[a-z0-9_]+|[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]+", p):
            piece = m.group(0)
            if _CJK_RE.fullmatch(piece):
                if len(piece) <= 4:
                    _add(piece)
                for i in range(len(piece) - 1):
                    _add(piece[i : i + 2])
            else:
                _add(piece)
    # Whole-query CJK bigrams when query is a continuous phrase
    for m in _CJK_RE.finditer(raw.replace(" ", "")):
        s = m.group(0)
        if len(s) >= 2:
            _add(s)
            for i in range(len(s) - 1):
                _add(s[i : i + 2])
    return out[:24]


def knowledge_cite_href(
    kb_id: str = "",
    *,
    kind: str = "doc",
    slug: str = "",
    doc_id: str = "",
    chunk_index: Optional[int] = None,
) -> str:
    """In-app path the chat UI can open as original preview."""
    kid = (kb_id or "").strip() or "local:default"
    if kid in {"default", "local"}:
        kid = "local:default"
    base = f"/knowledge/{quote(kid, safe='')}"
    if kind == "wiki":
        href = f"{base}/wiki/{quote(slug or 'page', safe='')}"
    elif doc_id:
        href = f"{base}/docs/{quote(doc_id, safe='')}"
    else:
        href = base
    if chunk_index is not None:
        href += f"#c{int(chunk_index)}"
    return href


def format_citation(
    *,
    title: str,
    source: str = "",
    source_uri: str = "",
    doc_id: str = "",
    chunk_index: Optional[int] = None,
    heading: str = "",
    context_header: str = "",
    kb_id: str = "",
) -> str:
    """Human-readable provenance line for chat / tool results."""
    label = (title or doc_id or "untitled").strip()
    path = (source_uri or "").strip()
    if not path and (source or "").startswith("file:"):
        path = source[5:]
    section = (context_header or heading or "").strip()
    if section:
        section = re.sub(r"^#+\s*", "", section.replace("\n", " › "))
    wiki = (source or "") == "wiki" or path.startswith("wiki:")
    if wiki:
        slug = path[5:] if path.startswith("wiki:") else path
        href = knowledge_cite_href(kb_id, kind="wiki", slug=slug, chunk_index=chunk_index)
        parts = [f"[{label}]({href})", f"`wiki:{slug or 'page'}`"]
        if section:
            parts.append(f"§ {section}")
        if chunk_index is not None:
            parts.append(f"chunk #{chunk_index}")
        if doc_id:
            parts.append(f"`doc:{doc_id}`")
        return " — ".join(parts)
    href = knowledge_cite_href(kb_id, kind="doc", doc_id=doc_id, chunk_index=chunk_index)
    parts = [f"[{label}]({href})"]
    if path:
        parts.append(f"`{path}`")
    elif source:
        parts.append(f"({source})")
    if section:
        parts.append(f"§ {section}")
    if chunk_index is not None:
        parts.append(f"chunk #{chunk_index}")
    if doc_id:
        parts.append(f"`doc:{doc_id}`")
    return " — ".join(parts)


def citations_markdown(hits: List[Dict[str, Any]]) -> str:
    if not hits:
        return ""
    lines = ["### Knowledge references"]
    for i, h in enumerate(hits, 1):
        cite = h.get("citation") or format_citation(
            title=str(h.get("title") or ""),
            source=str(h.get("source") or ""),
            source_uri=str(h.get("source_uri") or ""),
            doc_id=str(h.get("doc_id") or ""),
            chunk_index=h.get("chunk_index") if "chunk_index" in h else None,
            heading=str(h.get("heading") or ""),
            context_header=str(h.get("context_header") or ""),
            kb_id=str(h.get("kb_id") or ""),
        )
        snip = (h.get("snippet") or "").replace("\n", " ").strip()
        if len(snip) > 160:
            snip = snip[:157] + "…"
        lines.append(f"{i}. {cite}" + (f" — {snip}" if snip else ""))
    return "\n".join(lines)


def _heading_level(line: str) -> int:
    m = re.match(r"^(#{1,6})\s+\S", line)
    return len(m.group(1)) if m else 0


def _breadcrumb(stack: List[Tuple[int, str]]) -> str:
    if not stack:
        return ""
    return "\n".join(f"{'#' * lvl} {title}" for lvl, title in stack)


def _push_heading(stack: List[Tuple[int, str]], level: int, title: str) -> List[Tuple[int, str]]:
    next_stack = [(lvl, t) for lvl, t in stack if lvl < level]
    next_stack.append((level, title))
    return next_stack


CHUNK_STRATEGIES = ("heading", "parent_child", "fixed")


def parent_child_enabled() -> bool:
    import os

    v = (os.getenv("KB_PARENT_CHILD") or "1").strip().lower()
    return v not in {"0", "false", "no", "off"}


def normalize_chunk_strategy(strategy: str = "") -> str:
    s = (strategy or "").strip().lower().replace("-", "_")
    if s in {"heading", "headings", "markdown"}:
        return "heading"
    if s in {"fixed", "fixed_size", "size"}:
        return "fixed"
    if s in {"parent_child", "parent", "weknora"}:
        return "parent_child"
    if not s:
        return "parent_child" if parent_child_enabled() else "heading"
    return "parent_child"


def chunk_embedding_text(piece: Dict[str, Any]) -> str:
    """WeKnora-style EmbeddingContent: breadcrumb + body (header not in stored content)."""
    header = str(piece.get("context_header") or piece.get("heading") or "").strip()
    body = str(piece.get("content") or "").strip()
    if header and header not in body[: min(len(body), len(header) + 8)]:
        return f"{header}\n\n{body}"
    return body


def merge_breadcrumbs(parent: str, child: str) -> str:
    p = (parent or "").strip()
    c = (child or "").strip()
    if not p:
        return c
    if not c:
        return p
    if c.startswith(p):
        return c
    p_first = p.splitlines()[0]
    if c.splitlines()[0] == p_first:
        return c
    return f"{p}\n{c}"


def chunk_markdown(
    content: str,
    *,
    target: int = CHUNK_TARGET,
    overlap_ratio: float = CHUNK_OVERLAP_RATIO,
) -> List[Dict[str, Any]]:
    """Split markdown on headings / blank lines into ~target-char chunks with overlap."""
    text_body = content or ""
    if not text_body.strip():
        return []

    # Prefer heading boundaries, then blank-line paragraphs
    blocks: List[Tuple[str, str, int, str]] = []  # heading, text, start, breadcrumb
    heading = ""
    header = ""
    stack: List[Tuple[int, str]] = []
    buf: List[str] = []
    start = 0
    pos = 0
    lines = text_body.splitlines(keepends=True)
    for line in lines:
        level = _heading_level(line)
        if level:
            if buf:
                piece = "".join(buf)
                blocks.append((heading, piece, start, header))
                buf = []
            title = line.lstrip("#").strip()
            stack = _push_heading(stack, level, title)
            heading = title
            header = _breadcrumb(stack)
            start = pos
            buf.append(line)
        else:
            if not buf:
                start = pos
            buf.append(line)
            # flush oversized paragraph runs on blank lines
            if line.strip() == "" and sum(len(x) for x in buf) >= target:
                piece = "".join(buf)
                blocks.append((heading, piece, start, header))
                buf = []
        pos += len(line)
    if buf:
        blocks.append((heading, "".join(buf), start, header))

    # Re-pack blocks into target-sized chunks with overlap
    overlap = max(32, int(target * overlap_ratio))
    chunks: List[Dict[str, Any]] = []
    carry = ""
    carry_heading = ""
    carry_header = ""
    carry_start = 0
    for h, piece, st, crumb in blocks:
        heading_changed = bool(crumb) and bool(carry_header) and crumb != carry_header
        if carry and heading_changed:
            chunks.append(
                {
                    "heading": carry_heading,
                    "context_header": carry_header,
                    "content": carry.rstrip(),
                    "char_start": carry_start,
                    "char_end": carry_start + len(carry.rstrip()),
                    "chunk_type": "text",
                }
            )
            carry = ""
        section = piece
        sec_heading = h or carry_heading
        sec_header = crumb or carry_header
        sec_start = st
        if carry:
            section = carry + section
            sec_heading = carry_heading or h
            sec_header = carry_header or crumb
            sec_start = carry_start
            carry = ""
        while len(section) > target:
            cut = _soft_cut(section, target)
            chunk_text = section[:cut].rstrip()
            if chunk_text:
                chunks.append(
                    {
                        "heading": sec_heading,
                        "context_header": sec_header,
                        "content": chunk_text,
                        "char_start": sec_start,
                        "char_end": sec_start + len(chunk_text),
                        "chunk_type": "text",
                    }
                )
            # overlap window
            back = min(overlap, len(chunk_text))
            next_start_off = max(0, cut - back)
            sec_start = sec_start + next_start_off
            section = section[next_start_off:]
        carry = section
        carry_heading = sec_heading
        carry_header = sec_header
        carry_start = sec_start
    if carry.strip():
        chunks.append(
            {
                "heading": carry_heading,
                "context_header": carry_header,
                "content": carry.rstrip(),
                "char_start": carry_start,
                "char_end": carry_start + len(carry.rstrip()),
                "chunk_type": "text",
            }
        )
    if not chunks and text_body.strip():
        chunks.append(
            {
                "heading": "",
                "context_header": "",
                "content": text_body.strip(),
                "char_start": 0,
                "char_end": len(text_body.strip()),
                "chunk_type": "text",
            }
        )
    return chunks


def chunk_parent_child(
    content: str,
    *,
    parent_size: int = PARENT_CHUNK_TARGET,
    child_size: int = CHILD_CHUNK_TARGET,
    overlap_ratio: float = CHUNK_OVERLAP_RATIO,
) -> List[Dict[str, Any]]:
    """WeKnora-style two-level split: search children, answer from parent."""
    parents = chunk_markdown(content, target=parent_size, overlap_ratio=overlap_ratio)
    if not parents:
        return []
    out: List[Dict[str, Any]] = []
    for pi, parent in enumerate(parents):
        body = str(parent.get("content") or "")
        children = chunk_markdown(body, target=child_size, overlap_ratio=0.2)
        parent_header = str(parent.get("context_header") or parent.get("heading") or "")
        if len(children) <= 1:
            child = children[0] if children else parent
            out.append(
                {
                    **child,
                    "chunk_type": str(parent.get("chunk_type") or "text"),
                    "parent_index": -1,
                    "context_header": merge_breadcrumbs(
                        parent_header, str(child.get("context_header") or "")
                    ),
                    "char_start": int(parent.get("char_start") or 0),
                    "char_end": int(parent.get("char_end") or 0)
                    or int(parent.get("char_start") or 0) + len(body),
                }
            )
            continue
        out.append({**parent, "chunk_type": "parent", "parent_index": pi})
        p_start = int(parent.get("char_start") or 0)
        for child in children:
            header = merge_breadcrumbs(parent_header, str(child.get("context_header") or ""))
            out.append(
                {
                    **child,
                    "chunk_type": "text",
                    "parent_index": pi,
                    "context_header": header,
                    "char_start": p_start + int(child.get("char_start") or 0),
                    "char_end": p_start + int(child.get("char_end") or 0),
                }
            )
    return out


def chunk_fixed(
    content: str,
    *,
    target: int = CHUNK_TARGET,
    overlap_ratio: float = CHUNK_OVERLAP_RATIO,
) -> List[Dict[str, Any]]:
    """Fixed-size windows with soft punctuation cuts (no heading awareness)."""
    text_body = content or ""
    if not text_body.strip():
        return []
    size = max(64, int(target or CHUNK_TARGET))
    overlap = max(32, int(size * overlap_ratio))
    chunks: List[Dict[str, Any]] = []
    start = 0
    n = len(text_body)
    while start < n:
        window = text_body[start:]
        if len(window) <= size:
            piece = window.rstrip()
            if piece.strip():
                chunks.append(
                    {
                        "heading": "",
                        "context_header": "",
                        "content": piece,
                        "char_start": start,
                        "char_end": start + len(piece),
                        "chunk_type": "text",
                    }
                )
            break
        cut = _soft_cut(window, size)
        piece = window[:cut].rstrip()
        if piece.strip():
            chunks.append(
                {
                    "heading": "",
                    "context_header": "",
                    "content": piece,
                    "char_start": start,
                    "char_end": start + len(piece),
                    "chunk_type": "text",
                }
            )
        nxt = start + max(1, cut - overlap)
        if nxt <= start:
            nxt = start + cut
        start = nxt
    return chunks


def split_document(
    content: str,
    *,
    strategy: str = "",
    target: int = CHUNK_TARGET,
    child_size: int = CHILD_CHUNK_TARGET,
    parent_size: int = PARENT_CHUNK_TARGET,
    overlap_ratio: float = CHUNK_OVERLAP_RATIO,
) -> List[Dict[str, Any]]:
    kind = normalize_chunk_strategy(strategy)
    size = max(64, int(target or CHUNK_TARGET))
    child = max(64, int(child_size or CHILD_CHUNK_TARGET))
    parent = max(child, int(parent_size or PARENT_CHUNK_TARGET))
    overlap = float(overlap_ratio or CHUNK_OVERLAP_RATIO)
    if kind == "fixed":
        return chunk_fixed(content, target=size, overlap_ratio=overlap)
    if kind == "heading":
        return chunk_markdown(content, target=size, overlap_ratio=overlap)
    if len(content or "") > parent // 2:
        return chunk_parent_child(
            content, parent_size=parent, child_size=child, overlap_ratio=overlap
        )
    return chunk_markdown(content, target=size, overlap_ratio=overlap)


def preview_chunks(
    text: str,
    *,
    strategy: str = "",
    target: int = CHUNK_TARGET,
    child_size: int = CHILD_CHUNK_TARGET,
    parent_size: int = PARENT_CHUNK_TARGET,
    overlap_ratio: float = CHUNK_OVERLAP_RATIO,
    limit: int = 40,
) -> Dict[str, Any]:
    """In-memory chunker preview — no embeddings or SQLite writes."""
    body = text or ""
    kind = normalize_chunk_strategy(strategy)
    pieces = split_document(
        body,
        strategy=kind,
        target=target,
        child_size=child_size,
        parent_size=parent_size,
        overlap_ratio=overlap_ratio,
    )
    cap = max(1, min(int(limit or 40), 80))
    rows = []
    for i, piece in enumerate(pieces[:cap]):
        content = str(piece.get("content") or "")
        rows.append(
            {
                "index": i,
                "heading": piece.get("heading") or "",
                "context_header": piece.get("context_header") or "",
                "chunk_type": piece.get("chunk_type") or "text",
                "content": content,
                "chars": len(content),
                "char_start": int(piece.get("char_start") or 0),
                "char_end": int(piece.get("char_end") or 0),
            }
        )
    return {
        "strategy": kind,
        "count": len(pieces),
        "shown": len(rows),
        "params": {
            "target": max(64, int(target or CHUNK_TARGET)),
            "child_size": max(64, int(child_size or CHILD_CHUNK_TARGET)),
            "parent_size": max(64, int(parent_size or PARENT_CHUNK_TARGET)),
            "overlap_ratio": float(overlap_ratio or CHUNK_OVERLAP_RATIO),
        },
        "chunks": rows,
    }


def _soft_cut(s: str, target: int) -> int:
    if len(s) <= target:
        return len(s)
    window = s[: target + 40]
    # Prefer paragraph / sentence break near target
    for sep in ("\n\n", "\n", "。", ". ", "; ", "；", ", ", "，", " "):
        idx = window.rfind(sep)
        if idx >= int(target * 0.55):
            return idx + len(sep)
    return target


def _score_text(blob: str, title: str, tags: str, tokens: List[str], query: str) -> float:
    lower = (blob or "").lower()
    if not lower and not title:
        return 0.0
    score = 0.0
    q = (query or "").lower().strip()
    title_l = (title or "").lower()
    tags_l = (tags or "").lower()
    if q and q in lower:
        score += 5.0
    if q and q in title_l:
        score += 4.0
    for t in tokens:
        if t in title_l:
            score += 2.0
        if t in tags_l:
            score += 1.5
        score += min(3.0, lower.count(t) * 0.35)
    return score


class KnowledgeStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory
        self._fts_mode: Optional[str] = None  # trigram | unicode61 | None

    async def ensure_schema(self) -> None:
        async with self.session_factory() as session:
            conn = await session.connection()
            await conn.run_sync(Base.metadata.create_all)
            await session.commit()
        for ddl in (
            "ALTER TABLE knowledge_docs ADD COLUMN source_uri VARCHAR(1024) DEFAULT ''",
            "ALTER TABLE knowledge_docs ADD COLUMN content_hash VARCHAR(64) DEFAULT ''",
            "ALTER TABLE knowledge_docs ADD COLUMN kb_id VARCHAR(80) DEFAULT ''",
            "ALTER TABLE knowledge_docs ADD COLUMN parse_status VARCHAR(32) DEFAULT 'completed'",
            "ALTER TABLE knowledge_docs ADD COLUMN parse_error VARCHAR(1024) DEFAULT ''",
            "ALTER TABLE knowledge_chunks ADD COLUMN parent_chunk_id VARCHAR(80) DEFAULT ''",
            "ALTER TABLE knowledge_chunks ADD COLUMN chunk_type VARCHAR(32) DEFAULT 'text'",
            "ALTER TABLE knowledge_chunks ADD COLUMN context_header VARCHAR(1024) DEFAULT ''",
            "ALTER TABLE knowledge_chunks ADD COLUMN kb_id VARCHAR(80) DEFAULT ''",
            "ALTER TABLE knowledge_chunks ADD COLUMN embedding_model VARCHAR(128) DEFAULT ''",
            "ALTER TABLE knowledge_bases ADD COLUMN chunk_strategy VARCHAR(32) DEFAULT 'parent_child'",
        ):
            try:
                async with self.session_factory() as session:
                    await session.execute(text(ddl))
                    await session.commit()
            except Exception:
                pass
        async with self.session_factory() as session:
            try:
                await session.execute(
                    text(
                        "UPDATE knowledge_docs SET kb_id = :d "
                        "WHERE kb_id IS NULL OR kb_id = ''"
                    ),
                    {"d": DEFAULT_LOCAL_KB_ID},
                )
                await session.execute(
                    text(
                        "UPDATE knowledge_chunks SET kb_id = "
                        "(SELECT IFNULL(knowledge_docs.kb_id, :d) FROM knowledge_docs "
                        "WHERE knowledge_docs.doc_id = knowledge_chunks.doc_id) "
                        "WHERE kb_id IS NULL OR kb_id = ''"
                    ),
                    {"d": DEFAULT_LOCAL_KB_ID},
                )
                await session.commit()
            except Exception:
                await session.rollback()
        await self.ensure_default_kb()
        async with self.session_factory() as session:
            conn = await session.connection()
            self._fts_mode = await self._ensure_fts(conn)
            await session.commit()

    def _kb_values(self, kb_id: str = "") -> List[str]:
        return local_kb_match_values(kb_id)

    def _kb_filter_values(self, kb_id: str = "") -> Optional[List[str]]:
        """None means every local library (local:all)."""
        if is_all_local_kbs(kb_id):
            return None
        return local_kb_match_values(kb_id)

    def _with_kb(self, stmt, column, kb_id: str = ""):
        values = self._kb_filter_values(kb_id)
        if values is None:
            return stmt
        return stmt.where(column.in_(values))

    async def ensure_default_kb(self, workspace_id: str = "") -> Dict[str, Any]:
        async with self.session_factory() as session:
            row = (
                await session.execute(
                    select(KnowledgeBase).where(KnowledgeBase.kb_id == DEFAULT_LOCAL_KB_ID)
                )
            ).scalar_one_or_none()
            if row is None:
                row = KnowledgeBase(
                    kb_id=DEFAULT_LOCAL_KB_ID,
                    name=DEFAULT_LOCAL_KB_NAME,
                    description="本机 SQLite 默认库",
                    workspace_id=workspace_id or "",
                    chunk_strategy="parent_child",
                )
                session.add(row)
                await session.commit()
            return self._kb_public(row)

    @staticmethod
    def _kb_public(row: KnowledgeBase, *, doc_count: int = 0) -> Dict[str, Any]:
        return {
            "id": row.kb_id,
            "kb_id": row.kb_id,
            "name": row.name or DEFAULT_LOCAL_KB_NAME,
            "description": row.description or "",
            "workspace_id": row.workspace_id or "",
            "chunk_strategy": normalize_chunk_strategy(
                getattr(row, "chunk_strategy", "") or "parent_child"
            ),
            "source": "local",
            "doc_count": doc_count,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    @staticmethod
    def _job_public(row: KnowledgeIngestJob) -> Dict[str, Any]:
        return {
            "job_id": row.job_id,
            "kind": row.kind,
            "filename": row.filename,
            "source_uri": row.source_uri,
            "title": row.title,
            "status": row.status,
            "progress": int(row.progress or 0),
            "message": row.message or "",
            "error": row.error or "",
            "bytes": int(row.bytes_len or 0),
            "doc_id": row.doc_id or "",
            "kb_id": row.kb_id or "",
            "workspace_id": row.workspace_id or "",
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    async def _ensure_fts(self, conn) -> Optional[str]:
        existing = ""
        try:
            row = (
                await conn.execute(
                    text("SELECT sql FROM sqlite_master WHERE name='knowledge_chunks_fts'")
                )
            ).first()
            existing = str(row[0] or "") if row else ""
        except Exception:
            existing = ""
        if existing:
            mode = "trigram" if "trigram" in existing else "unicode61"
            await self._backfill_fts_if_empty(conn)
            return mode
        for tokenizer in ("trigram", "unicode61"):
            ddl = (
                "CREATE VIRTUAL TABLE knowledge_chunks_fts USING fts5("
                "chunk_id UNINDEXED, doc_id UNINDEXED, heading, context_header, content, "
                f"tokenize='{tokenizer}')"
            )
            try:
                await conn.execute(text(ddl))
                await self._backfill_fts_if_empty(conn)
                return tokenizer
            except Exception:
                continue
        return None

    async def _backfill_fts_if_empty(self, conn) -> None:
        """Copy existing chunks into a newly created / empty FTS table."""
        try:
            row = (await conn.execute(text("SELECT COUNT(*) FROM knowledge_chunks_fts"))).first()
            n = int(row[0] or 0) if row else 0
        except Exception:
            return
        if n > 0:
            return
        try:
            await conn.execute(
                text(
                    "INSERT INTO knowledge_chunks_fts"
                    "(chunk_id, doc_id, heading, context_header, content) "
                    "SELECT chunk_id, doc_id, IFNULL(heading,''), "
                    "IFNULL(context_header,''), IFNULL(content,'') "
                    "FROM knowledge_chunks "
                    "WHERE IFNULL(chunk_type, 'text') != 'parent'"
                )
            )
        except Exception:
            logger.debug("knowledge FTS backfill skipped", exc_info=True)

    def _fts_match_query(self, query: str) -> str:
        q = (query or "").strip()
        if not q:
            return ""
        if self._fts_mode == "trigram":
            return '"' + q.replace('"', '""') + '"'
        tokens = _tokens(q)
        parts = ['"' + t.replace('"', '""') + '"' for t in tokens if t]
        return " OR ".join(parts) if parts else '"' + q.replace('"', '""') + '"'

    async def _replace_fts_doc(
        self,
        session: AsyncSession,
        doc_id: str,
        rows: List[Tuple[str, str, str, str, str]],
    ) -> None:
        if not self._fts_mode:
            return
        try:
            await session.execute(
                text("DELETE FROM knowledge_chunks_fts WHERE doc_id = :d"),
                {"d": doc_id},
            )
            for chunk_id, heading, header, content, ctype in rows:
                if (ctype or "text") == "parent":
                    continue
                await session.execute(
                    text(
                        "INSERT INTO knowledge_chunks_fts"
                        "(chunk_id, doc_id, heading, context_header, content) "
                        "VALUES (:id, :doc, :h, :ctx, :c)"
                    ),
                    {
                        "id": chunk_id,
                        "doc": doc_id,
                        "h": heading or "",
                        "ctx": header or "",
                        "c": content or "",
                    },
                )
        except Exception:
            logger.warning("knowledge FTS upsert failed for %s", doc_id, exc_info=True)

    async def _fts_chunk_ids(
        self, session: AsyncSession, query: str, *, limit: int = 160
    ) -> List[str]:
        if not self._fts_mode:
            return []
        match = self._fts_match_query(query)
        if not match:
            return []
        try:
            result = await session.execute(
                text(
                    "SELECT chunk_id FROM knowledge_chunks_fts "
                    "WHERE knowledge_chunks_fts MATCH :q ORDER BY rank LIMIT :lim"
                ),
                {"q": match, "lim": limit},
            )
            return [str(r[0]) for r in result.fetchall() if r and r[0]]
        except Exception:
            return []

    async def upsert(
        self,
        *,
        doc_id: str,
        title: str,
        content: str,
        tags: str = "",
        source: str = "",
        source_uri: str = "",
        workspace_id: str = "",
        kb_id: str = "",
        parse_status: str = "completed",
        parse_error: str = "",
        content_hash_value: Optional[str] = None,
        skip_if_unchanged: bool = False,
        force_chunk_type: str = "",
    ) -> Dict[str, Any]:
        body = content or ""
        digest = content_hash_value or content_hash(body)
        local_id = normalize_local_kb_id(kb_id)
        chunk_cfg = await self.get_chunk_settings(local_id)
        async with self.session_factory() as session:
            row = (
                await session.execute(select(KnowledgeDoc).where(KnowledgeDoc.doc_id == doc_id))
            ).scalar_one_or_none()
            if row is None:
                row = KnowledgeDoc(doc_id=doc_id)
                session.add(row)
            elif skip_if_unchanged and (row.content_hash or "") == digest and (row.content or "") == body:
                return {**self._public(row), "unchanged": True}

            row.title = title or row.title or doc_id
            row.content = body
            row.tags = tags if tags is not None else (row.tags or "")
            if source:
                row.source = source
            if source_uri:
                row.source_uri = source_uri
            elif source.startswith("file:"):
                row.source_uri = source[5:]
            row.content_hash = digest
            row.workspace_id = workspace_id or row.workspace_id or ""
            row.kb_id = local_id or row.kb_id or DEFAULT_LOCAL_KB_ID
            row.parse_status = parse_status or "completed"
            row.parse_error = parse_error or ""
            row.updated_at = datetime.now(timezone.utc)
            await session.flush()

            await session.execute(delete(KnowledgeChunk).where(KnowledgeChunk.doc_id == doc_id))
            pieces = split_document(
                body,
                strategy=str(chunk_cfg.get("strategy") or ""),
                target=int(chunk_cfg.get("target") or CHUNK_TARGET),
                child_size=int(chunk_cfg.get("child_size") or CHILD_CHUNK_TARGET),
                parent_size=int(chunk_cfg.get("parent_size") or PARENT_CHUNK_TARGET),
                overlap_ratio=float(chunk_cfg.get("overlap_ratio") or CHUNK_OVERLAP_RATIO),
            )
            parent_ids: Dict[int, str] = {}
            for i, piece in enumerate(pieces):
                if str(piece.get("chunk_type") or "") == "parent":
                    parent_ids[int(piece.get("parent_index") or i)] = f"{doc_id}#{i}"
            embeddable = [
                (i, p)
                for i, p in enumerate(pieces)
                if str(p.get("chunk_type") or "text") != "parent"
            ]
            emb_by_index: Dict[int, List[float]] = {}
            embed_ep = resolve_embedding_endpoint()
            if (embeddings_configured() or embed_ep) and embeddable:
                raw = await embed_texts(
                    [chunk_embedding_text(p) for _, p in embeddable],
                    endpoint=embed_ep,
                )
                if raw:
                    for (idx, _), vec in zip(embeddable, raw):
                        if vec:
                            emb_by_index[idx] = vec
            image_vec: Optional[List[float]] = None
            src_path = ""
            if (source or "").startswith("file:"):
                src_path = source[5:]
            elif source_uri:
                src_path = source_uri
            if (
                multimodal_embeddings_enabled()
                and src_path
                and re.search(r"\.(png|jpe?g|webp|gif|bmp)$", src_path, re.I)
            ):
                image_vec = await embed_one_image(src_path)

            fts_rows: List[Tuple[str, str, str, str, str]] = []

            for i, piece in enumerate(pieces):
                ctype = str(piece.get("chunk_type") or "text")
                if force_chunk_type and ctype != "parent":
                    ctype = force_chunk_type[:32]
                parent_id = ""
                pidx = piece.get("parent_index")
                if pidx is not None and int(pidx) >= 0:
                    parent_id = parent_ids.get(int(pidx), "")
                emb_json = ""
                vec = emb_by_index.get(i)
                if image_vec and ctype != "parent" and not vec:
                    vec = image_vec
                    if ctype == "text":
                        ctype = "image"
                if vec:
                    emb_json = serialize_embedding(vec)
                chunk_id = f"{doc_id}#{i}"
                heading = str(piece.get("heading") or "")[:512]
                context_header = str(piece.get("context_header") or "")[:1024]
                body_piece = str(piece.get("content") or "")
                session.add(
                    KnowledgeChunk(
                        chunk_id=chunk_id,
                        doc_id=doc_id,
                        chunk_index=i,
                        heading=heading,
                        context_header=context_header,
                        content=body_piece,
                        char_start=int(piece.get("char_start") or 0),
                        char_end=int(piece.get("char_end") or 0),
                        embedding=emb_json,
                        embedding_model=(embed_ep.model if emb_json and embed_ep else "")[:128],
                        parent_chunk_id=parent_id[:80],
                        chunk_type=ctype[:32],
                        workspace_id=row.workspace_id,
                        kb_id=row.kb_id or DEFAULT_LOCAL_KB_ID,
                        updated_at=datetime.now(timezone.utc),
                    )
                )
                fts_rows.append((chunk_id, heading, context_header, body_piece, ctype))
            await self._replace_fts_doc(session, doc_id, fts_rows)
            await session.commit()
            return self._public(row)

    async def delete(self, doc_id: str) -> bool:
        async with self.session_factory() as session:
            if self._fts_mode:
                try:
                    await session.execute(
                        text("DELETE FROM knowledge_chunks_fts WHERE doc_id = :d"),
                        {"d": doc_id},
                    )
                except Exception:
                    pass
            await session.execute(delete(KnowledgeChunk).where(KnowledgeChunk.doc_id == doc_id))
            res = await session.execute(delete(KnowledgeDoc).where(KnowledgeDoc.doc_id == doc_id))
            await session.commit()
            return (res.rowcount or 0) > 0

    async def get(self, doc_id: str, *, include_chunks: bool = False) -> Optional[Dict[str, Any]]:
        async with self.session_factory() as session:
            row = (
                await session.execute(select(KnowledgeDoc).where(KnowledgeDoc.doc_id == doc_id))
            ).scalar_one_or_none()
            if not row:
                return None
            out = self._public(row)
            if include_chunks:
                chunks = (
                    await session.execute(
                        select(KnowledgeChunk)
                        .where(KnowledgeChunk.doc_id == doc_id)
                        .order_by(KnowledgeChunk.chunk_index.asc())
                    )
                ).scalars().all()
                out["chunks"] = [self._chunk_public(c) for c in chunks]
            return out

    async def read(
        self,
        doc_id: str,
        *,
        offset: int = 0,
        limit: int = 4000,
        chunk_index: Optional[int] = None,
        neighbors: int = 0,
    ) -> Optional[Dict[str, Any]]:
        """Return a content window or a chunk with optional neighbors."""
        async with self.session_factory() as session:
            row = (
                await session.execute(select(KnowledgeDoc).where(KnowledgeDoc.doc_id == doc_id))
            ).scalar_one_or_none()
            if not row:
                return None
            body = row.content or ""
            if chunk_index is not None:
                chunks = (
                    await session.execute(
                        select(KnowledgeChunk)
                        .where(KnowledgeChunk.doc_id == doc_id)
                        .order_by(KnowledgeChunk.chunk_index.asc())
                    )
                ).scalars().all()
                if not chunks:
                    return {
                        **self._public(row, include_content=False),
                        "offset": 0,
                        "limit": len(body),
                        "total": len(body),
                        "text": body,
                        "chunks": [],
                    }
                idx = max(0, min(int(chunk_index), len(chunks) - 1))
                lo = max(0, idx - max(0, neighbors))
                hi = min(len(chunks), idx + max(0, neighbors) + 1)
                selected = chunks[lo:hi]
                return {
                    **self._public(row, include_content=False),
                    "chunk_index": idx,
                    "neighbors": neighbors,
                    "text": "\n\n".join(c.content for c in selected),
                    "chunks": [self._chunk_public(c) for c in selected],
                    "total_chunks": len(chunks),
                }

            off = max(0, int(offset or 0))
            lim = max(1, min(int(limit or 4000), 50_000))
            slice_text = body[off : off + lim]
            return {
                **self._public(row, include_content=False),
                "offset": off,
                "limit": lim,
                "total": len(body),
                "text": slice_text,
                "truncated": off + lim < len(body),
            }

    async def list_docs(
        self, workspace_id: str = "", limit: int = 50, *, tag: str = "", kb_id: str = ""
    ) -> List[Dict[str, Any]]:
        async with self.session_factory() as session:
            stmt = select(KnowledgeDoc).order_by(KnowledgeDoc.updated_at.desc()).limit(limit)
            if workspace_id:
                stmt = stmt.where(
                    or_(KnowledgeDoc.workspace_id == workspace_id, KnowledgeDoc.workspace_id == "")
                )
            if kb_id is not None:
                stmt = stmt.where(KnowledgeDoc.kb_id.in_(self._kb_values(kb_id)))
            tag_s = (tag or "").strip()
            if tag_s:
                stmt = stmt.where(KnowledgeDoc.tags.ilike(f"%{tag_s}%"))
            if not tag_s.startswith("session:"):
                stmt = stmt.where(KnowledgeDoc.source != "session-upload")
                stmt = stmt.where(KnowledgeDoc.source != "wiki")
            rows = (await session.execute(stmt)).scalars().all()
            return [self._public(r, include_content=False) for r in rows]

    async def list_local_kbs(self, workspace_id: str = "") -> List[Dict[str, Any]]:
        await self.ensure_default_kb(workspace_id)
        async with self.session_factory() as session:
            stmt = select(KnowledgeBase).order_by(KnowledgeBase.created_at.asc())
            if workspace_id:
                stmt = stmt.where(
                    or_(
                        KnowledgeBase.workspace_id == workspace_id,
                        KnowledgeBase.workspace_id == "",
                        KnowledgeBase.kb_id == DEFAULT_LOCAL_KB_ID,
                    )
                )
            rows = list((await session.execute(stmt)).scalars().all())
            counts: Dict[str, int] = {}
            count_stmt = select(KnowledgeDoc.kb_id, func.count()).group_by(KnowledgeDoc.kb_id)
            if workspace_id:
                count_stmt = count_stmt.where(
                    or_(KnowledgeDoc.workspace_id == workspace_id, KnowledgeDoc.workspace_id == "")
                )
            count_stmt = count_stmt.where(KnowledgeDoc.source != "session-upload")
            for kb, n in (await session.execute(count_stmt)).all():
                counts[str(kb or "")] = int(n or 0)
            out = []
            seen = set()
            for row in rows:
                seen.add(row.kb_id)
                n = int(counts.get(row.kb_id, 0))
                if row.kb_id == DEFAULT_LOCAL_KB_ID:
                    n += int(counts.get("", 0))
                out.append(self._kb_public(row, doc_count=n))
            if DEFAULT_LOCAL_KB_ID not in seen:
                out.insert(
                    0,
                    {
                        "id": DEFAULT_LOCAL_KB_ID,
                        "kb_id": DEFAULT_LOCAL_KB_ID,
                        "name": DEFAULT_LOCAL_KB_NAME,
                        "description": "本机 SQLite 默认库",
                        "workspace_id": workspace_id or "",
                        "chunk_strategy": "parent_child",
                        "source": "local",
                        "doc_count": int(counts.get(DEFAULT_LOCAL_KB_ID, 0) + counts.get("", 0)),
                        "updated_at": None,
                    },
                )
            return out

    async def create_local_kb(
        self,
        *,
        name: str,
        workspace_id: str = "",
        description: str = "",
        chunk_strategy: str = "",
    ) -> Dict[str, Any]:
        label = (name or "").strip() or "未命名知识库"
        kb_id = f"local:{uuid4().hex[:10]}"
        strategy = normalize_chunk_strategy(chunk_strategy or "parent_child")
        async with self.session_factory() as session:
            row = KnowledgeBase(
                kb_id=kb_id,
                name=label[:256],
                description=(description or "")[:1024],
                workspace_id=workspace_id or "",
                chunk_strategy=strategy,
            )
            session.add(row)
            await session.commit()
            return self._kb_public(row, doc_count=0)

    async def get_local_kb(self, kb_id: str) -> Optional[Dict[str, Any]]:
        nid = normalize_local_kb_id(kb_id)
        async with self.session_factory() as session:
            row = (
                await session.execute(select(KnowledgeBase).where(KnowledgeBase.kb_id == nid))
            ).scalar_one_or_none()
            return self._kb_public(row) if row else None

    async def get_chunk_settings(self, kb_id: str = "") -> Dict[str, Any]:
        nid = normalize_local_kb_id(kb_id)
        strategy = ""
        async with self.session_factory() as session:
            row = (
                await session.execute(select(KnowledgeBase).where(KnowledgeBase.kb_id == nid))
            ).scalar_one_or_none()
            if row is not None:
                strategy = getattr(row, "chunk_strategy", "") or ""
        kind = normalize_chunk_strategy(strategy)
        return {
            "strategy": kind,
            "target": CHUNK_TARGET,
            "child_size": CHILD_CHUNK_TARGET,
            "parent_size": PARENT_CHUNK_TARGET,
            "overlap_ratio": CHUNK_OVERLAP_RATIO,
        }

    async def update_local_kb(
        self,
        kb_id: str,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
        chunk_strategy: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        nid = normalize_local_kb_id(kb_id)
        async with self.session_factory() as session:
            row = (
                await session.execute(select(KnowledgeBase).where(KnowledgeBase.kb_id == nid))
            ).scalar_one_or_none()
            if row is None:
                if nid != DEFAULT_LOCAL_KB_ID:
                    return None
                row = KnowledgeBase(
                    kb_id=DEFAULT_LOCAL_KB_ID,
                    name=DEFAULT_LOCAL_KB_NAME,
                    description="本机 SQLite 默认库",
                    chunk_strategy="parent_child",
                )
                session.add(row)
            if name is not None:
                label = str(name).strip()
                if label:
                    row.name = label[:256]
            if description is not None:
                row.description = str(description)[:1024]
            if chunk_strategy is not None:
                row.chunk_strategy = normalize_chunk_strategy(chunk_strategy)
            row.updated_at = datetime.now(timezone.utc)
            await session.commit()
            return self._kb_public(row)

    async def delete_local_kb(self, kb_id: str) -> bool:
        nid = normalize_local_kb_id(kb_id)
        if nid == DEFAULT_LOCAL_KB_ID:
            raise ValueError("cannot delete the default knowledge base")
        async with self.session_factory() as session:
            docs = list(
                (
                    await session.execute(select(KnowledgeDoc.doc_id).where(KnowledgeDoc.kb_id == nid))
                ).scalars().all()
            )
            for doc_id in docs:
                if self._fts_mode:
                    try:
                        await session.execute(
                            text("DELETE FROM knowledge_chunks_fts WHERE doc_id = :d"),
                            {"d": doc_id},
                        )
                    except Exception:
                        pass
            if docs:
                await session.execute(delete(KnowledgeChunk).where(KnowledgeChunk.kb_id == nid))
                await session.execute(delete(KnowledgeDoc).where(KnowledgeDoc.kb_id == nid))
            page_ids = list(
                (
                    await session.execute(
                        select(KnowledgeWikiPage.page_id).where(KnowledgeWikiPage.kb_id == nid)
                    )
                ).scalars().all()
            )
            if page_ids:
                await session.execute(
                    delete(KnowledgeWikiLink).where(KnowledgeWikiLink.from_page_id.in_(page_ids))
                )
                await session.execute(
                    delete(KnowledgeWikiRevision).where(KnowledgeWikiRevision.page_id.in_(page_ids))
                )
                await session.execute(delete(KnowledgeWikiPage).where(KnowledgeWikiPage.kb_id == nid))
            await session.execute(delete(KnowledgeGraphNode).where(KnowledgeGraphNode.kb_id == nid))
            await session.execute(delete(KnowledgeGraphEdge).where(KnowledgeGraphEdge.kb_id == nid))
            res = await session.execute(delete(KnowledgeBase).where(KnowledgeBase.kb_id == nid))
            await session.commit()
            return (res.rowcount or 0) > 0

    async def create_ingest_job(
        self,
        *,
        job_id: str,
        kind: str = "file",
        filename: str = "",
        source_uri: str = "",
        kb_id: str = "",
        workspace_id: str = "",
        bytes_len: int = 0,
        title: str = "",
        status: str = "pending",
        progress: int = 0,
        message: str = "",
    ) -> Dict[str, Any]:
        async with self.session_factory() as session:
            row = KnowledgeIngestJob(
                job_id=job_id,
                kind=(kind or "file")[:16],
                filename=(filename or "")[:512],
                source_uri=(source_uri or "")[:2048],
                title=(title or "")[:512],
                status=status or "pending",
                progress=int(progress or 0),
                message=(message or "")[:512],
                bytes_len=int(bytes_len or 0),
                kb_id=normalize_local_kb_id(kb_id),
                workspace_id=workspace_id or "",
            )
            session.add(row)
            await session.commit()
            return self._job_public(row)

    async def get_ingest_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        async with self.session_factory() as session:
            row = (
                await session.execute(
                    select(KnowledgeIngestJob).where(KnowledgeIngestJob.job_id == job_id)
                )
            ).scalar_one_or_none()
            return self._job_public(row) if row else None

    async def update_ingest_job(self, job_id: str, **fields: Any) -> Dict[str, Any]:
        async with self.session_factory() as session:
            row = (
                await session.execute(
                    select(KnowledgeIngestJob).where(KnowledgeIngestJob.job_id == job_id)
                )
            ).scalar_one_or_none()
            if not row:
                raise ValueError(f"job not found: {job_id}")
            mapping = {
                "status": "status",
                "progress": "progress",
                "message": "message",
                "error": "error",
                "doc_id": "doc_id",
                "bytes_len": "bytes_len",
                "filename": "filename",
                "source_uri": "source_uri",
                "title": "title",
            }
            for key, attr in mapping.items():
                if key in fields and fields[key] is not None:
                    val = fields[key]
                    if attr == "progress":
                        val = int(val)
                    elif attr == "bytes_len":
                        val = int(val)
                    elif isinstance(val, str) and attr in {"status", "message", "filename", "title"}:
                        val = val[:512]
                    setattr(row, attr, val)
            row.updated_at = datetime.now(timezone.utc)
            await session.commit()
            return self._job_public(row)

    async def list_ingest_jobs(
        self,
        *,
        workspace_id: str = "",
        kb_id: str = "",
        limit: int = 40,
        status_in: Optional[Sequence[str]] = None,
    ) -> List[Dict[str, Any]]:
        async with self.session_factory() as session:
            stmt = select(KnowledgeIngestJob).order_by(KnowledgeIngestJob.created_at.desc())
            stmt = stmt.limit(max(1, min(int(limit or 40), 200)))
            if workspace_id:
                stmt = stmt.where(
                    or_(
                        KnowledgeIngestJob.workspace_id == workspace_id,
                        KnowledgeIngestJob.workspace_id == "",
                    )
                )
            if kb_id:
                stmt = stmt.where(KnowledgeIngestJob.kb_id.in_(self._kb_values(kb_id)))
            if status_in:
                stmt = stmt.where(KnowledgeIngestJob.status.in_(list(status_in)))
            rows = list((await session.execute(stmt)).scalars().all())
            return [self._job_public(r) for r in rows]

    async def update_chunk(
        self,
        chunk_id: str,
        *,
        content: Optional[str] = None,
        heading: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        async with self.session_factory() as session:
            row = (
                await session.execute(
                    select(KnowledgeChunk).where(KnowledgeChunk.chunk_id == chunk_id)
                )
            ).scalar_one_or_none()
            if not row:
                return None
            if heading is not None:
                row.heading = str(heading)[:512]
            if content is not None:
                row.content = str(content)
                embed_ep = resolve_embedding_endpoint()
                if (embeddings_configured() or embed_ep) and (
                    getattr(row, "chunk_type", "") or "text"
                ) != "parent":
                    header = getattr(row, "context_header", "") or ""
                    text_in = f"{header}\n{row.content}".strip() if header else row.content
                    vecs = await embed_texts([text_in], endpoint=embed_ep)
                    if vecs and vecs[0]:
                        row.embedding = serialize_embedding(vecs[0])
                        row.embedding_model = (embed_ep.model if embed_ep else "")[:128]
            row.updated_at = datetime.now(timezone.utc)
            if self._fts_mode and (getattr(row, "chunk_type", "") or "text") != "parent":
                try:
                    await session.execute(
                        text("DELETE FROM knowledge_chunks_fts WHERE chunk_id = :id"),
                        {"id": chunk_id},
                    )
                    await session.execute(
                        text(
                            "INSERT INTO knowledge_chunks_fts"
                            "(chunk_id, doc_id, heading, context_header, content) "
                            "VALUES (:id, :doc, :h, :ctx, :c)"
                        ),
                        {
                            "id": row.chunk_id,
                            "doc": row.doc_id,
                            "h": row.heading or "",
                            "ctx": getattr(row, "context_header", "") or "",
                            "c": row.content or "",
                        },
                    )
                except Exception:
                    logger.warning("knowledge FTS chunk update failed for %s", chunk_id, exc_info=True)
            await session.commit()
            return self._chunk_public(row)

    async def find_by_content_hash(
        self,
        digest: str,
        *,
        workspace_id: str = "",
    ) -> Optional[Dict[str, Any]]:
        """Return a local doc with this content_hash. Prefer non-weknora_* ids."""
        key = (digest or "").strip()
        if not key:
            return None
        async with self.session_factory() as session:
            stmt = select(KnowledgeDoc).where(KnowledgeDoc.content_hash == key)
            if workspace_id:
                stmt = stmt.where(
                    or_(
                        KnowledgeDoc.workspace_id == workspace_id,
                        KnowledgeDoc.workspace_id == "",
                    )
                )
            rows = list((await session.execute(stmt)).scalars().all())
        if not rows:
            return None
        preferred = [r for r in rows if not (r.doc_id or "").startswith("weknora_")]
        return self._public(preferred[0] if preferred else rows[0])

    async def find_by_source_uri(
        self,
        source_uri: str,
        *,
        workspace_id: str = "",
    ) -> Optional[Dict[str, Any]]:
        uri = (source_uri or "").strip()
        if not uri:
            return None
        async with self.session_factory() as session:
            stmt = select(KnowledgeDoc).where(KnowledgeDoc.source_uri == uri)
            if workspace_id:
                stmt = stmt.where(
                    or_(
                        KnowledgeDoc.workspace_id == workspace_id,
                        KnowledgeDoc.workspace_id == "",
                    )
                )
            rows = list((await session.execute(stmt)).scalars().all())
        if not rows:
            return None
        preferred = [r for r in rows if not (r.doc_id or "").startswith("weknora_")]
        return self._public(preferred[0] if preferred else rows[0])

    async def search(
        self,
        query: str,
        *,
        workspace_id: str = "",
        limit: int = 8,
        tag: str = "",
        session_id: str = "",
        kb_id: str = "",
        embedding_provider: str = "",
        embedding_model: str = "",
    ) -> List[Dict[str, Any]]:
        from src.core_kernel.plugin_runtime.knowledge_query import (
            expand_queries,
            merge_hits_by_id,
            should_expand,
        )
        from src.core_kernel.plugin_runtime.knowledge_rerank import rerank_hits

        q = (query or "").strip()
        pool = max(limit * 3, 16)
        hits = await self._search_once(
            q,
            workspace_id=workspace_id,
            limit=pool,
            tag=tag,
            session_id=session_id,
            kb_id=kb_id,
            embedding_provider=embedding_provider,
            embedding_model=embedding_model,
        )
        if should_expand(len(hits), limit):
            extras: List[Dict[str, Any]] = []
            for variant in expand_queries(q):
                extras.extend(
                    await self._search_once(
                        variant,
                        workspace_id=workspace_id,
                        limit=pool,
                        query_vec=None,
                        skip_vector=True,
                        tag=tag,
                        session_id=session_id,
                        kb_id=kb_id,
                        embedding_provider=embedding_provider,
                        embedding_model=embedding_model,
                    )
                )
            hits = merge_hits_by_id(hits, extras, limit=pool)
        return await rerank_hits(q, hits, keep=limit)

    def _is_searchable_chunk(self, chunk: KnowledgeChunk) -> bool:
        ctype = (getattr(chunk, "chunk_type", None) or "text").strip() or "text"
        return ctype != "parent"

    def _doc_visible_for_session(self, doc: KnowledgeDoc, session_id: str = "") -> bool:
        return row_visible_for_session(
            {"source": getattr(doc, "source", None) or "", "tags": getattr(doc, "tags", None) or ""},
            session_id,
        )

    async def _search_once(
        self,
        query: str,
        *,
        workspace_id: str = "",
        limit: int = 8,
        query_vec: Optional[List[float]] = None,
        skip_vector: bool = False,
        tag: str = "",
        session_id: str = "",
        kb_id: str = "",
        embedding_provider: str = "",
        embedding_model: str = "",
    ) -> List[Dict[str, Any]]:
        tokens = _tokens(query)
        q = (query or "").strip()
        embed_ep = resolve_embedding_endpoint(embedding_provider, embedding_model)
        use_vec = bool(q) and not skip_vector and (embeddings_configured() or embed_ep)
        if use_vec and query_vec is None:
            query_vec = await embed_one(q, endpoint=embed_ep)

        async with self.session_factory() as session:
            ws_filter = None
            if workspace_id:
                ws_filter = or_(
                    KnowledgeChunk.workspace_id == workspace_id,
                    KnowledgeChunk.workspace_id == "",
                )
            not_parent = or_(
                KnowledgeChunk.chunk_type != "parent",
                KnowledgeChunk.chunk_type == "",
                KnowledgeChunk.chunk_type.is_(None),
            )

            # --- Keyword candidate pool (FTS5 when available, else ILIKE) ---
            kw_chunks: List[KnowledgeChunk] = []
            fts_ids = await self._fts_chunk_ids(session, q, limit=160) if q else []
            if fts_ids:
                stmt = select(KnowledgeChunk).where(KnowledgeChunk.chunk_id.in_(fts_ids))
                stmt = stmt.where(not_parent)
                stmt = self._with_kb(stmt, KnowledgeChunk.kb_id, kb_id)
                if ws_filter is not None:
                    stmt = stmt.where(ws_filter)
                kw_chunks = list((await session.execute(stmt)).scalars().all())
            if not kw_chunks and q:
                likes = []
                likes.append(KnowledgeChunk.content.ilike(f"%{q}%"))
                likes.append(KnowledgeChunk.heading.ilike(f"%{q}%"))
                likes.append(KnowledgeChunk.context_header.ilike(f"%{q}%"))
                for t in tokens:
                    likes.append(KnowledgeChunk.content.ilike(f"%{t}%"))
                    likes.append(KnowledgeChunk.heading.ilike(f"%{t}%"))
                    likes.append(KnowledgeChunk.context_header.ilike(f"%{t}%"))
                stmt = select(KnowledgeChunk).where(not_parent)
                stmt = self._with_kb(stmt, KnowledgeChunk.kb_id, kb_id)
                if ws_filter is not None:
                    stmt = stmt.where(ws_filter)
                stmt = stmt.where(or_(*likes)).limit(160)
                kw_chunks = list((await session.execute(stmt)).scalars().all())

            # --- Vector candidate pool (even when keyword miss) ---
            vec_chunks: List[KnowledgeChunk] = []
            if query_vec is not None:
                vstmt = (
                    select(KnowledgeChunk)
                    .where(KnowledgeChunk.embedding != "")
                    .where(not_parent)
                )
                vstmt = self._with_kb(vstmt, KnowledgeChunk.kb_id, kb_id)
                want_model = (embed_ep.model if embed_ep else embedding_model) or ""
                if want_model:
                    vstmt = vstmt.where(
                        or_(
                            KnowledgeChunk.embedding_model == want_model,
                            KnowledgeChunk.embedding_model == "",
                            KnowledgeChunk.embedding_model.is_(None),
                        )
                    )
                if ws_filter is not None:
                    vstmt = vstmt.where(ws_filter)
                vec_limit = 800 if is_all_local_kbs(kb_id) else 400
                vstmt = vstmt.order_by(KnowledgeChunk.updated_at.desc()).limit(vec_limit)
                vec_chunks = list((await session.execute(vstmt)).scalars().all())

            by_id: Dict[str, KnowledgeChunk] = {}
            for c in kw_chunks:
                if self._is_searchable_chunk(c):
                    by_id[c.chunk_id] = c
            for c in vec_chunks:
                if self._is_searchable_chunk(c):
                    by_id.setdefault(c.chunk_id, c)
            chunks = list(by_id.values())

            if not chunks:
                # Legacy whole-doc fallback when nothing chunked yet
                return await self._search_docs(
                    session, query, tokens, workspace_id, limit, session_id=session_id, kb_id=kb_id
                )

            extra_ids = {c.parent_chunk_id for c in chunks if getattr(c, "parent_chunk_id", "")}
            extra_ids.discard("")
            extra_ids |= {c.chunk_id for c in chunks}
            parents_by_id: Dict[str, KnowledgeChunk] = {}
            if extra_ids:
                prows = (
                    await session.execute(
                        select(KnowledgeChunk).where(KnowledgeChunk.chunk_id.in_(list(extra_ids)))
                    )
                ).scalars().all()
                parents_by_id = {p.chunk_id: p for p in prows}

            doc_ids = {c.doc_id for c in chunks}
            docs_by_id: Dict[str, KnowledgeDoc] = {}
            if doc_ids:
                drows = (
                    await session.execute(
                        select(KnowledgeDoc).where(KnowledgeDoc.doc_id.in_(list(doc_ids)))
                    )
                ).scalars().all()
                docs_by_id = {d.doc_id: d for d in drows}

        scored: List[Tuple[float, KnowledgeChunk, KnowledgeDoc]] = []
        for c in chunks:
            doc = docs_by_id.get(c.doc_id)
            if not doc:
                continue
            if not self._doc_visible_for_session(doc, session_id):
                continue
            header = getattr(c, "context_header", "") or ""
            kw = _score_text(
                f"{header}\n{c.heading}\n{c.content}",
                doc.title or "",
                doc.tags or "",
                tokens,
                query,
            )
            vec_score = 0.0
            if query_vec:
                emb = deserialize_embedding(c.embedding)
                if emb:
                    vec_score = cosine_similarity(query_vec, emb) * 6.0
            total = kw + vec_score
            # Pure semantic: keep decent cosine hits even with kw=0
            if total <= 0 and tokens and not query_vec:
                continue
            if query_vec and kw <= 0 and vec_score < 1.2:
                continue
            scored.append((total, c, doc))

        tag_s = (tag or "").strip().lower()
        if tag_s:
            scored = [row for row in scored if tag_s in (row[2].tags or "").lower()]

        scored.sort(key=lambda x: x[0], reverse=True)
        out: List[Dict[str, Any]] = []
        seen_docs: set[str] = set()
        for sc, c, doc in scored:
            if doc.doc_id in seen_docs and len(out) >= max(2, limit // 2):
                continue
            seen_docs.add(doc.doc_id)
            header = getattr(c, "context_header", "") or ""
            cite = format_citation(
                title=doc.title or "",
                source=doc.source or "",
                source_uri=getattr(doc, "source_uri", "") or "",
                doc_id=doc.doc_id,
                chunk_index=c.chunk_index,
                heading=c.heading or "",
                context_header=header,
                kb_id=getattr(doc, "kb_id", "") or kb_id,
            )
            display = c.content or ""
            parent = parents_by_id.get(getattr(c, "parent_chunk_id", "") or "")
            if parent and parent.content and len(display) < SHORT_CHUNK_EXPAND:
                display = parent.content
            snap = build_text_snapshot(display, query=q, tokens=tokens or [query])
            item = {
                "doc_id": doc.doc_id,
                "chunk_id": c.chunk_id,
                "chunk_index": c.chunk_index,
                "title": doc.title,
                "heading": c.heading,
                "context_header": header,
                "parent_chunk_id": getattr(c, "parent_chunk_id", "") or "",
                "chunk_type": getattr(c, "chunk_type", "") or "text",
                "tags": doc.tags,
                "source": doc.source,
                "source_uri": getattr(doc, "source_uri", "") or "",
                "workspace_id": doc.workspace_id,
                "kb_id": getattr(doc, "kb_id", "") or "",
                "score": round(sc, 3),
                "snippet": snap.get("snippet") or self._snippet(display, tokens or [query]),
                "snapshot": snap,
                "match_start": snap.get("match_start"),
                "match_end": snap.get("match_end"),
                "match_text": snap.get("match_text") or "",
                "match_kind": snap.get("match_kind") or "",
                "citation": cite,
                "cite_href": knowledge_cite_href(
                    getattr(doc, "kb_id", "") or kb_id,
                    kind="wiki" if (doc.source or "") == "wiki" else "doc",
                    slug=(getattr(doc, "source_uri", "") or "")[5:]
                    if (doc.source or "") == "wiki"
                    and str(getattr(doc, "source_uri", "") or "").startswith("wiki:")
                    else "",
                    doc_id=doc.doc_id,
                    chunk_index=c.chunk_index,
                ),
                "cite_kind": "wiki" if (doc.source or "") == "wiki" else "doc",
                "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
            }
            out.append(item)
            if len(out) >= limit:
                break
        return out

    async def _search_docs(
        self,
        session: AsyncSession,
        query: str,
        tokens: List[str],
        workspace_id: str,
        limit: int,
        *,
        session_id: str = "",
        kb_id: str = "",
    ) -> List[Dict[str, Any]]:
        stmt = select(KnowledgeDoc)
        if workspace_id:
            stmt = stmt.where(
                or_(KnowledgeDoc.workspace_id == workspace_id, KnowledgeDoc.workspace_id == "")
            )
        stmt = self._with_kb(stmt, KnowledgeDoc.kb_id, kb_id)
        likes = []
        q = (query or "").strip()
        if q:
            likes.append(KnowledgeDoc.title.ilike(f"%{q}%"))
            likes.append(KnowledgeDoc.content.ilike(f"%{q}%"))
            likes.append(KnowledgeDoc.tags.ilike(f"%{q}%"))
        for t in tokens:
            likes.append(KnowledgeDoc.title.ilike(f"%{t}%"))
            likes.append(KnowledgeDoc.content.ilike(f"%{t}%"))
            likes.append(KnowledgeDoc.tags.ilike(f"%{t}%"))
        if likes:
            stmt = stmt.where(or_(*likes))
        stmt = stmt.limit(80)
        rows = list((await session.execute(stmt)).scalars().all())
        scored = [
            (_score_text(r.content or "", r.title or "", r.tags or "", tokens, query), r)
            for r in rows
            if self._doc_visible_for_session(r, session_id)
        ]
        scored.sort(key=lambda x: x[0], reverse=True)
        out = []
        for sc, r in scored[:limit]:
            if sc <= 0 and tokens:
                continue
            item = self._public(r, include_content=False)
            item["score"] = round(sc, 3)
            snap = build_text_snapshot(r.content or "", query=q, tokens=tokens or [query])
            item["snippet"] = snap.get("snippet") or self._snippet(r.content or "", tokens or [query])
            item["snapshot"] = snap
            item["match_start"] = snap.get("match_start")
            item["match_end"] = snap.get("match_end")
            item["match_text"] = snap.get("match_text") or ""
            item["match_kind"] = snap.get("match_kind") or ""
            item["doc_id"] = r.doc_id
            item["citation"] = format_citation(
                title=r.title or "",
                source=r.source or "",
                source_uri=getattr(r, "source_uri", "") or "",
                doc_id=r.doc_id,
                kb_id=getattr(r, "kb_id", "") or kb_id,
            )
            item["cite_href"] = knowledge_cite_href(
                getattr(r, "kb_id", "") or kb_id,
                kind="wiki" if (r.source or "") == "wiki" else "doc",
                slug=(getattr(r, "source_uri", "") or "")[5:]
                if (r.source or "") == "wiki"
                and str(getattr(r, "source_uri", "") or "").startswith("wiki:")
                else "",
                doc_id=r.doc_id,
            )
            item["cite_kind"] = "wiki" if (r.source or "") == "wiki" else "doc"
            out.append(item)
        return out

    async def stats(self, workspace_id: str = "", kb_id: str = "") -> Dict[str, Any]:
        async with self.session_factory() as session:
            doc_stmt = select(func.count()).select_from(KnowledgeDoc)
            chunk_stmt = select(func.count()).select_from(KnowledgeChunk)
            emb_stmt = (
                select(func.count())
                .select_from(KnowledgeChunk)
                .where(KnowledgeChunk.embedding != "")
            )
            doc_stmt = self._with_kb(doc_stmt, KnowledgeDoc.kb_id, kb_id)
            chunk_stmt = self._with_kb(chunk_stmt, KnowledgeChunk.kb_id, kb_id)
            emb_stmt = self._with_kb(emb_stmt, KnowledgeChunk.kb_id, kb_id)
            if workspace_id:
                ws_docs = or_(
                    KnowledgeDoc.workspace_id == workspace_id,
                    KnowledgeDoc.workspace_id == "",
                )
                ws_chunks = or_(
                    KnowledgeChunk.workspace_id == workspace_id,
                    KnowledgeChunk.workspace_id == "",
                )
                doc_stmt = doc_stmt.where(ws_docs)
                chunk_stmt = chunk_stmt.where(ws_chunks)
                emb_stmt = emb_stmt.where(ws_chunks)
            doc_stmt = doc_stmt.where(KnowledgeDoc.source != "wiki")
            docs = int((await session.execute(doc_stmt)).scalar() or 0)
            chunks = int((await session.execute(chunk_stmt)).scalar() or 0)
            embedded = int((await session.execute(emb_stmt)).scalar() or 0)
            wiki_stmt = select(func.count()).select_from(KnowledgeWikiPage)
            wiki_stmt = self._with_kb(wiki_stmt, KnowledgeWikiPage.kb_id, kb_id)
            wiki_pages = int((await session.execute(wiki_stmt)).scalar() or 0)
        info = effective_embedding_stats()
        choices: List[Dict[str, Any]] = []
        default_emb = ""
        try:
            from src.core_kernel.plugin_runtime.knowledge_embeddings import env_embedding_public
            from src.core_kernel.model_gateway.provider_store import ProviderStore

            env_row = env_embedding_public()
            if env_row.get("configured"):
                choices.append(
                    {
                        "id": "env",
                        "label": env_row.get("label") or "环境变量",
                        "model": env_row.get("default_model") or "",
                        "source": "env",
                    }
                )
            store = ProviderStore()
            default_emb = store.default_embedding_provider or default_emb
            for p in store.providers_of_kind("embedding"):
                if not p.enabled:
                    continue
                pub = ProviderStore.to_public(p)
                choices.append(
                    {
                        "id": p.id,
                        "label": pub.get("label") or p.id,
                        "model": p.default_model or (p.models[0] if p.models else ""),
                        "source": "settings",
                    }
                )
        except Exception:
            default_emb = ""
        return {
            "docs": docs,
            "wiki_pages": wiki_pages,
            "chunks": chunks,
            "chunks_with_embedding": embedded,
            "embeddings_configured": bool(info.get("configured")),
            "embedding_backend": info.get("backend") or "",
            "embedding_model": info.get("model") or "",
            "embedding_provider": info.get("provider_id") or "",
            "embedding_source": info.get("source") or "",
            "embedding_dim": info.get("dim") or 0,
            "embedding_multimodal": bool(info.get("multimodal")),
            "embedding_choices": choices,
            "default_embedding_provider": default_emb,
            "hybrid_ready": bool(info.get("configured")) and embedded > 0,
            "parent_child": parent_child_enabled(),
            "fts5": bool(self._fts_mode),
            "fts5_tokenizer": self._fts_mode or "",
        }

    async def patch(
        self,
        doc_id: str,
        *,
        title: Optional[str] = None,
        content: Optional[str] = None,
        tags: Optional[str] = None,
        source: Optional[str] = None,
        source_uri: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Partial update; re-chunks when content changes."""
        existing = await self.get(doc_id)
        if not existing:
            return None
        new_title = title if title is not None else existing.get("title") or doc_id
        new_content = content if content is not None else existing.get("content") or ""
        new_tags = tags if tags is not None else existing.get("tags") or ""
        new_source = source if source is not None else existing.get("source") or ""
        new_uri = source_uri if source_uri is not None else existing.get("source_uri") or ""
        # Metadata-only updates must not hit skip_if_unchanged (that would ignore title).
        if content is None and (
            title is not None or tags is not None or source is not None or source_uri is not None
        ):
            async with self.session_factory() as session:
                row = (
                    await session.execute(
                        select(KnowledgeDoc).where(KnowledgeDoc.doc_id == doc_id)
                    )
                ).scalar_one_or_none()
                if not row:
                    return None
                if title is not None:
                    row.title = str(title)
                if tags is not None:
                    row.tags = str(tags)
                if source is not None:
                    row.source = str(source)
                if source_uri is not None:
                    row.source_uri = str(source_uri)
                row.updated_at = datetime.now(timezone.utc)
                await session.commit()
                return self._public(row)
        return await self.upsert(
            doc_id=doc_id,
            title=str(new_title),
            content=str(new_content),
            tags=str(new_tags),
            source=str(new_source),
            source_uri=str(new_uri),
            workspace_id=str(existing.get("workspace_id") or ""),
            kb_id=str(existing.get("kb_id") or ""),
            content_hash_value=content_hash(str(new_content)),
            skip_if_unchanged=False,
        )

    def _wiki_public(
        self,
        row: KnowledgeWikiPage,
        *,
        include_content: bool = True,
        revisions: Optional[List[Dict[str, Any]]] = None,
        links_out: Optional[List[Dict[str, Any]]] = None,
        links_in: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "page_id": row.page_id,
            "kb_id": row.kb_id,
            "slug": row.slug,
            "title": row.title,
            "status": row.status or "published",
            "source_doc_ids": _json_list(row.source_doc_ids),
            "content_hash": row.content_hash or "",
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        if include_content:
            out["content"] = row.content or ""
        else:
            out["content_len"] = len(row.content or "")
        if revisions is not None:
            out["revisions"] = revisions
        if links_out is not None:
            out["links_out"] = links_out
        if links_in is not None:
            out["links_in"] = links_in
        return out

    @staticmethod
    def _revision_public(row: KnowledgeWikiRevision) -> Dict[str, Any]:
        return {
            "revision_id": row.revision_id,
            "page_id": row.page_id,
            "title": row.title,
            "author": row.author,
            "message": row.message or "",
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "content_len": len(row.content or ""),
        }

    @staticmethod
    def _link_public(row: KnowledgeWikiLink) -> Dict[str, Any]:
        return {
            "from_page_id": row.from_page_id,
            "to_kind": row.to_kind,
            "to_id": row.to_id,
            "label": row.label or "",
            "raw": row.raw or "",
        }

    @staticmethod
    def _node_public(row: KnowledgeGraphNode) -> Dict[str, Any]:
        attrs: Any = {}
        try:
            attrs = json.loads(row.attrs or "{}")
        except Exception:
            attrs = {}
        return {
            "node_id": row.node_id,
            "kb_id": row.kb_id,
            "kind": row.kind,
            "label": row.label,
            "page_id": row.page_id or "",
            "doc_id": row.doc_id or "",
            "source_doc_id": row.source_doc_id or "",
            "attrs": attrs if isinstance(attrs, dict) else {},
        }

    @staticmethod
    def _edge_public(row: KnowledgeGraphEdge) -> Dict[str, Any]:
        return {
            "edge_id": row.edge_id,
            "kb_id": row.kb_id,
            "from_id": row.from_id,
            "to_id": row.to_id,
            "rel": row.rel,
            "weight": float(row.weight or 1.0),
            "evidence": row.evidence or "",
            "source_doc_id": row.source_doc_id or "",
        }

    async def list_wiki_pages(
        self, kb_id: str = "", *, limit: int = 200, status: str = ""
    ) -> List[Dict[str, Any]]:
        local_id = normalize_local_kb_id(kb_id)
        async with self.session_factory() as session:
            stmt = (
                select(KnowledgeWikiPage)
                .where(KnowledgeWikiPage.kb_id.in_(self._kb_values(local_id)))
                .order_by(KnowledgeWikiPage.updated_at.desc())
                .limit(max(1, min(int(limit or 200), 500)))
            )
            if status:
                stmt = stmt.where(KnowledgeWikiPage.status == status)
            rows = (await session.execute(stmt)).scalars().all()
            return [self._wiki_public(r, include_content=False) for r in rows]

    async def get_wiki_page(
        self,
        kb_id: str,
        slug: str,
        *,
        include_revisions: bool = True,
        include_content: bool = True,
    ) -> Optional[Dict[str, Any]]:
        local_id = normalize_local_kb_id(kb_id)
        slug_s = (slug or "").strip()
        if not slug_s:
            return None
        async with self.session_factory() as session:
            row = (
                await session.execute(
                    select(KnowledgeWikiPage).where(
                        KnowledgeWikiPage.kb_id.in_(self._kb_values(local_id)),
                        KnowledgeWikiPage.slug == slug_s,
                    )
                )
            ).scalar_one_or_none()
            if not row:
                return None
            revisions: List[Dict[str, Any]] = []
            if include_revisions:
                revs = (
                    await session.execute(
                        select(KnowledgeWikiRevision)
                        .where(KnowledgeWikiRevision.page_id == row.page_id)
                        .order_by(KnowledgeWikiRevision.created_at.desc())
                        .limit(40)
                    )
                ).scalars().all()
                revisions = [self._revision_public(r) for r in revs]
            links_out = (
                await session.execute(
                    select(KnowledgeWikiLink).where(KnowledgeWikiLink.from_page_id == row.page_id)
                )
            ).scalars().all()
            links_in = (
                await session.execute(
                    select(KnowledgeWikiLink).where(
                        KnowledgeWikiLink.to_kind == "page",
                        KnowledgeWikiLink.to_id == row.slug,
                    )
                )
            ).scalars().all()
            return self._wiki_public(
                row,
                include_content=include_content,
                revisions=revisions,
                links_out=[self._link_public(x) for x in links_out],
                links_in=[self._link_public(x) for x in links_in],
            )

    async def get_wiki_page_by_id(self, page_id: str) -> Optional[Dict[str, Any]]:
        async with self.session_factory() as session:
            row = (
                await session.execute(
                    select(KnowledgeWikiPage).where(KnowledgeWikiPage.page_id == page_id)
                )
            ).scalar_one_or_none()
            return self._wiki_public(row) if row else None

    async def list_wiki_revisions(self, page_id: str, *, limit: int = 40) -> List[Dict[str, Any]]:
        async with self.session_factory() as session:
            rows = (
                await session.execute(
                    select(KnowledgeWikiRevision)
                    .where(KnowledgeWikiRevision.page_id == page_id)
                    .order_by(KnowledgeWikiRevision.created_at.desc())
                    .limit(max(1, min(int(limit or 40), 100)))
                )
            ).scalars().all()
            return [self._revision_public(r) for r in rows]

    async def wiki_page_is_user_dirty(self, page_id: str) -> bool:
        revs = await self.list_wiki_revisions(page_id, limit=40)
        if not revs:
            return False
        latest = revs[0]
        if str(latest.get("author") or "") != "user":
            return False
        last_agent = next((r for r in revs if str(r.get("author") or "") == "agent"), None)
        if not last_agent:
            return True
        async with self.session_factory() as session:
            latest_row = (
                await session.execute(
                    select(KnowledgeWikiRevision).where(
                        KnowledgeWikiRevision.revision_id == str(latest.get("revision_id") or "")
                    )
                )
            ).scalar_one_or_none()
            agent_row = (
                await session.execute(
                    select(KnowledgeWikiRevision).where(
                        KnowledgeWikiRevision.revision_id == str(last_agent.get("revision_id") or "")
                    )
                )
            ).scalar_one_or_none()
        user_hash = content_hash((latest_row.content if latest_row else "") or "")
        agent_hash = content_hash((agent_row.content if agent_row else "") or "")
        return user_hash != agent_hash

    async def replace_wiki_links(
        self, page_id: str, links: Sequence[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        async with self.session_factory() as session:
            await session.execute(
                delete(KnowledgeWikiLink).where(KnowledgeWikiLink.from_page_id == page_id)
            )
            out: List[KnowledgeWikiLink] = []
            for item in links:
                row = KnowledgeWikiLink(
                    from_page_id=page_id,
                    to_kind=str(item.get("to_kind") or "page")[:16],
                    to_id=str(item.get("to_id") or "")[:160],
                    label=str(item.get("label") or "")[:256],
                    raw=str(item.get("raw") or "")[:512],
                )
                session.add(row)
                out.append(row)
            await session.commit()
            return [self._link_public(r) for r in out]

    async def save_wiki_page(
        self,
        *,
        kb_id: str,
        slug: str,
        title: str,
        content: str,
        author: str = "user",
        message: str = "",
        status: str = "published",
        source_doc_ids: Optional[Sequence[str]] = None,
        page_id: str = "",
        workspace_id: str = "",
    ) -> Dict[str, Any]:
        from src.core_kernel.plugin_runtime.knowledge_wiki import parse_wikilinks

        local_id = normalize_local_kb_id(kb_id)
        slug_s = (slug or "").strip()
        if not slug_s:
            raise ValueError("slug required")
        body = content or ""
        digest = content_hash(body)
        async with self.session_factory() as session:
            row = (
                await session.execute(
                    select(KnowledgeWikiPage).where(
                        KnowledgeWikiPage.kb_id == local_id,
                        KnowledgeWikiPage.slug == slug_s,
                    )
                )
            ).scalar_one_or_none()
            now = datetime.now(timezone.utc)
            if row is None:
                row = KnowledgeWikiPage(
                    page_id=page_id or f"wpg_{uuid4().hex[:16]}",
                    kb_id=local_id,
                    slug=slug_s,
                    created_at=now,
                )
                session.add(row)
            elif page_id and row.page_id != page_id:
                row = KnowledgeWikiPage(
                    page_id=page_id,
                    kb_id=local_id,
                    slug=slug_s,
                    created_at=now,
                )
                session.add(row)
            row.title = (title or row.title or slug_s)[:512]
            row.content = body
            row.status = (status or "published")[:32]
            if source_doc_ids is not None:
                row.source_doc_ids = json.dumps(_json_list(list(source_doc_ids)), ensure_ascii=False)
            row.content_hash = digest
            row.updated_at = now
            await session.flush()
            rev = KnowledgeWikiRevision(
                revision_id=f"wrev_{uuid4().hex[:16]}",
                page_id=row.page_id,
                title=row.title,
                content=body,
                author=(author if author in {"user", "agent"} else "user")[:16],
                message=(message or "")[:512],
                created_at=now,
            )
            session.add(rev)
            await session.commit()
            saved = self._wiki_public(row)
        links = parse_wikilinks(body)
        await self.replace_wiki_links(saved["page_id"], links)
        await self.upsert(
            doc_id=wiki_index_doc_id(saved["page_id"]),
            title=saved["title"],
            content=body,
            tags="wiki",
            source="wiki",
            source_uri=f"wiki:{saved['slug']}",
            workspace_id=workspace_id,
            kb_id=local_id,
            content_hash_value=digest,
            force_chunk_type="wiki",
        )
        await self.sync_wiki_page_graph(local_id, saved["page_id"])
        return (await self.get_wiki_page(local_id, slug_s)) or saved

    async def rollback_wiki_page(
        self, kb_id: str, slug: str, revision_id: str, *, author: str = "user"
    ) -> Dict[str, Any]:
        page = await self.get_wiki_page(kb_id, slug, include_revisions=False)
        if not page:
            raise ValueError("wiki page not found")
        async with self.session_factory() as session:
            rev = (
                await session.execute(
                    select(KnowledgeWikiRevision).where(
                        KnowledgeWikiRevision.revision_id == revision_id,
                        KnowledgeWikiRevision.page_id == str(page.get("page_id") or ""),
                    )
                )
            ).scalar_one_or_none()
            if not rev:
                raise ValueError("revision not found")
            title = rev.title
            body = rev.content or ""
        return await self.save_wiki_page(
            kb_id=kb_id,
            slug=slug,
            title=title,
            content=body,
            author=author,
            message=f"rollback to {revision_id}",
            status=str(page.get("status") or "published"),
            source_doc_ids=page.get("source_doc_ids") or [],
            workspace_id="",
        )

    async def upsert_graph_node(
        self,
        *,
        kb_id: str,
        node_id: str,
        kind: str,
        label: str,
        page_id: str = "",
        doc_id: str = "",
        source_doc_id: str = "",
        attrs: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        local_id = normalize_local_kb_id(kb_id)
        async with self.session_factory() as session:
            row = (
                await session.execute(
                    select(KnowledgeGraphNode).where(KnowledgeGraphNode.node_id == node_id)
                )
            ).scalar_one_or_none()
            if row is None:
                row = KnowledgeGraphNode(node_id=node_id)
                session.add(row)
            row.kb_id = local_id
            row.kind = (kind or "entity")[:16]
            row.label = (label or node_id)[:512]
            row.page_id = (page_id or "")[:64]
            row.doc_id = (doc_id or "")[:64]
            row.source_doc_id = (source_doc_id or "")[:64]
            row.attrs = json.dumps(attrs or {}, ensure_ascii=False)
            await session.commit()
            return self._node_public(row)

    async def upsert_graph_edge(
        self,
        *,
        kb_id: str,
        from_id: str,
        to_id: str,
        rel: str,
        weight: float = 1.0,
        evidence: str = "",
        source_doc_id: str = "",
        edge_id: str = "",
    ) -> Dict[str, Any]:
        local_id = normalize_local_kb_id(kb_id)
        eid = edge_id or (
            "e_"
            + hashlib.sha1(f"{local_id}:{from_id}:{to_id}:{rel}".encode("utf-8")).hexdigest()[:16]
        )
        async with self.session_factory() as session:
            row = (
                await session.execute(
                    select(KnowledgeGraphEdge).where(KnowledgeGraphEdge.edge_id == eid)
                )
            ).scalar_one_or_none()
            if row is None:
                row = KnowledgeGraphEdge(edge_id=eid)
                session.add(row)
            row.kb_id = local_id
            row.from_id = from_id
            row.to_id = to_id
            row.rel = (rel or "related")[:32]
            row.weight = float(weight or 1.0)
            row.evidence = (evidence or "")[:1024]
            row.source_doc_id = (source_doc_id or "")[:64]
            await session.commit()
            return self._edge_public(row)

    async def delete_graph_for_sources(self, kb_id: str, source_doc_ids: Sequence[str]) -> None:
        local_id = normalize_local_kb_id(kb_id)
        ids = [str(x) for x in source_doc_ids if str(x).strip()]
        if not ids:
            return
        async with self.session_factory() as session:
            await session.execute(
                delete(KnowledgeGraphNode).where(
                    KnowledgeGraphNode.kb_id == local_id,
                    KnowledgeGraphNode.source_doc_id.in_(ids),
                )
            )
            await session.execute(
                delete(KnowledgeGraphEdge).where(
                    KnowledgeGraphEdge.kb_id == local_id,
                    KnowledgeGraphEdge.source_doc_id.in_(ids),
                )
            )
            await session.commit()

    async def sync_wiki_page_graph(self, kb_id: str, page_id: str) -> None:
        page = await self.get_wiki_page_by_id(page_id)
        if not page:
            return
        local_id = normalize_local_kb_id(kb_id or str(page.get("kb_id") or ""))
        slug = str(page.get("slug") or "")
        node_id = f"page:{page_id}"
        sources = _json_list(page.get("source_doc_ids"))
        source_doc = sources[0] if sources else ""
        await self.upsert_graph_node(
            kb_id=local_id,
            node_id=node_id,
            kind="page",
            label=str(page.get("title") or slug),
            page_id=page_id,
            source_doc_id=source_doc,
            attrs={"slug": slug},
        )
        async with self.session_factory() as session:
            await session.execute(
                delete(KnowledgeGraphEdge).where(
                    KnowledgeGraphEdge.kb_id == local_id,
                    KnowledgeGraphEdge.from_id == node_id,
                    KnowledgeGraphEdge.rel == "wiki_link",
                )
            )
            await session.commit()
        links = (
            await self.get_wiki_page(local_id, slug, include_revisions=False)
        ) or {}
        for link in links.get("links_out") or []:
            to_kind = str(link.get("to_kind") or "page")
            to_id = str(link.get("to_id") or "")
            if not to_id:
                continue
            if to_kind == "doc":
                dest = f"doc:{to_id}"
                await self.upsert_graph_node(
                    kb_id=local_id,
                    node_id=dest,
                    kind="doc",
                    label=to_id,
                    doc_id=to_id,
                    source_doc_id=to_id,
                )
                rel = "mentions"
            else:
                dest_page = await self.get_wiki_page(local_id, to_id, include_revisions=False)
                if dest_page:
                    dest = f"page:{dest_page['page_id']}"
                else:
                    dest = f"page-slug:{to_id}"
                    await self.upsert_graph_node(
                        kb_id=local_id,
                        node_id=dest,
                        kind="page",
                        label=str(link.get("label") or to_id),
                        attrs={"slug": to_id, "missing": True},
                    )
                rel = "wiki_link"
            await self.upsert_graph_edge(
                kb_id=local_id,
                from_id=node_id,
                to_id=dest,
                rel=rel,
                evidence=str(link.get("raw") or ""),
                source_doc_id=source_doc,
            )

    async def list_graph(
        self, kb_id: str = "", *, q: str = "", limit: int = 80
    ) -> Dict[str, Any]:
        local_id = normalize_local_kb_id(kb_id)
        cap = max(8, min(int(limit or 80), 200))
        query = (q or "").strip().lower()
        async with self.session_factory() as session:
            nstmt = select(KnowledgeGraphNode).where(
                KnowledgeGraphNode.kb_id.in_(self._kb_values(local_id))
            )
            nodes = list((await session.execute(nstmt)).scalars().all())
            estmt = select(KnowledgeGraphEdge).where(
                KnowledgeGraphEdge.kb_id.in_(self._kb_values(local_id))
            )
            edges = list((await session.execute(estmt)).scalars().all())
        if query:
            seed = {
                n.node_id
                for n in nodes
                if query in (n.label or "").lower()
                or query in (n.kind or "").lower()
                or query in (n.page_id or "").lower()
                or query in (n.doc_id or "").lower()
            }
            extra: set[str] = set()
            for e in edges:
                if e.from_id in seed:
                    extra.add(e.to_id)
                if e.to_id in seed:
                    extra.add(e.from_id)
            keep = seed | extra
            nodes = [n for n in nodes if n.node_id in keep]
            edges = [e for e in edges if e.from_id in keep and e.to_id in keep]
        if len(nodes) > cap:
            rank = {"page": 0, "doc": 1, "entity": 2}
            nodes.sort(key=lambda n: (rank.get(n.kind, 9), n.label or ""))
            keep_ids = {n.node_id for n in nodes[:cap]}
            nodes = [n for n in nodes if n.node_id in keep_ids]
            edges = [e for e in edges if e.from_id in keep_ids and e.to_id in keep_ids]
        return {
            "kb_id": local_id,
            "nodes": [self._node_public(n) for n in nodes],
            "edges": [self._edge_public(e) for e in edges],
        }

    async def graph_neighbors(self, node_id: str, *, limit: int = 40) -> Dict[str, Any]:
        nid = (node_id or "").strip()
        if not nid:
            return {"node": None, "nodes": [], "edges": []}
        cap = max(1, min(int(limit or 40), 80))
        async with self.session_factory() as session:
            center = (
                await session.execute(
                    select(KnowledgeGraphNode).where(KnowledgeGraphNode.node_id == nid)
                )
            ).scalar_one_or_none()
            edges = list(
                (
                    await session.execute(
                        select(KnowledgeGraphEdge).where(
                            or_(
                                KnowledgeGraphEdge.from_id == nid,
                                KnowledgeGraphEdge.to_id == nid,
                            )
                        )
                    )
                ).scalars().all()
            )[:cap]
            ids = {nid}
            for e in edges:
                ids.add(e.from_id)
                ids.add(e.to_id)
            nodes = list(
                (
                    await session.execute(
                        select(KnowledgeGraphNode).where(KnowledgeGraphNode.node_id.in_(list(ids)))
                    )
                ).scalars().all()
            )
        return {
            "node": self._node_public(center) if center else None,
            "nodes": [self._node_public(n) for n in nodes],
            "edges": [self._edge_public(e) for e in edges],
        }

    async def reindex_embeddings(
        self,
        *,
        workspace_id: str = "",
        kb_id: str = "",
        limit: int = 200,
        embedding_provider: str = "",
        embedding_model: str = "",
        force: bool = False,
    ) -> Dict[str, Any]:
        """Embed chunks missing vectors when a settings or env embedding endpoint exists."""
        embed_ep = resolve_embedding_endpoint(embedding_provider, embedding_model)
        if not embeddings_configured() and not embed_ep:
            return {
                "ok": False,
                "error": "embeddings not configured（请在设置 → 模型 → 向量模型中配置，或设置 KB_EMBEDDING_*）",
                "updated": 0,
            }
        want_model = (embed_ep.model if embed_ep else embedding_model) or ""
        async with self.session_factory() as session:
            stmt = select(KnowledgeChunk).where(
                or_(
                    KnowledgeChunk.chunk_type != "parent",
                    KnowledgeChunk.chunk_type == "",
                    KnowledgeChunk.chunk_type.is_(None),
                )
            )
            if not force:
                missing = or_(
                    KnowledgeChunk.embedding == "",
                    KnowledgeChunk.embedding.is_(None),
                )
                if want_model:
                    stmt = stmt.where(
                        or_(
                            missing,
                            KnowledgeChunk.embedding_model == "",
                            KnowledgeChunk.embedding_model.is_(None),
                            KnowledgeChunk.embedding_model != want_model,
                        )
                    )
                else:
                    stmt = stmt.where(missing)
            stmt = stmt.order_by(KnowledgeChunk.updated_at.desc()).limit(max(1, min(limit, 500)))
            if workspace_id:
                stmt = stmt.where(
                    or_(
                        KnowledgeChunk.workspace_id == workspace_id,
                        KnowledgeChunk.workspace_id == "",
                    )
                )
            stmt = self._with_kb(stmt, KnowledgeChunk.kb_id, kb_id)
            rows = list((await session.execute(stmt)).scalars().all())
            if not rows:
                return {
                    "ok": True,
                    "updated": 0,
                    "scanned": 0,
                    "embedding_model": want_model,
                    "embedding_provider": embed_ep.provider_id if embed_ep else "",
                }

            texts = [
                chunk_embedding_text(
                    {
                        "content": r.content or "",
                        "context_header": getattr(r, "context_header", "") or "",
                        "heading": r.heading or "",
                    }
                )
                for r in rows
            ]
            # Batch in groups of 32
            updated = 0
            errors: List[str] = []
            for i in range(0, len(texts), 32):
                batch_rows = rows[i : i + 32]
                batch_texts = texts[i : i + 32]
                vectors = await embed_texts(batch_texts, endpoint=embed_ep)
                if not vectors:
                    errors.append(f"embed batch@{i} failed")
                    continue
                for row, vec in zip(batch_rows, vectors):
                    if not vec:
                        continue
                    row.embedding = serialize_embedding(vec)
                    if want_model:
                        row.embedding_model = want_model[:128]
                    row.updated_at = datetime.now(timezone.utc)
                    updated += 1
            await session.commit()
        return {
            "ok": True,
            "scanned": len(rows),
            "updated": updated,
            "errors": errors[:10],
            "embedding_model": want_model,
            "embedding_provider": embed_ep.provider_id if embed_ep else "",
        }

    async def rechunk_doc(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Re-split one document using the bound library's current chunk strategy."""
        existing = await self.get(doc_id)
        if not existing:
            return None
        body = str(existing.get("content") or "")
        return await self.upsert(
            doc_id=doc_id,
            title=str(existing.get("title") or doc_id),
            content=body,
            tags=str(existing.get("tags") or ""),
            source=str(existing.get("source") or ""),
            source_uri=str(existing.get("source_uri") or ""),
            workspace_id=str(existing.get("workspace_id") or ""),
            kb_id=str(existing.get("kb_id") or ""),
            parse_status=str(existing.get("parse_status") or "completed"),
            content_hash_value=str(existing.get("content_hash") or content_hash(body)),
            skip_if_unchanged=False,
        )

    async def rechunk_library(
        self, *, kb_id: str = "", workspace_id: str = "", limit: int = 40
    ) -> Dict[str, Any]:
        docs = await self.list_docs(
            workspace_id=workspace_id,
            limit=max(1, min(int(limit or 40), 80)),
            kb_id=kb_id,
        )
        updated = 0
        errors: List[str] = []
        for doc in docs:
            did = str(doc.get("doc_id") or "")
            if not did:
                continue
            try:
                row = await self.rechunk_doc(did)
                if row:
                    updated += 1
            except Exception as exc:
                errors.append(f"{did}: {exc}")
        return {
            "ok": True,
            "scanned": len(docs),
            "updated": updated,
            "errors": errors[:20],
        }

    async def log_sync(
        self,
        *,
        source: str,
        source_uri: str = "",
        content_hash_value: str = "",
        status: str = "ok",
        message: str = "",
        workspace_id: str = "",
    ) -> None:
        async with self.session_factory() as session:
            session.add(
                KnowledgeSyncLog(
                    source=source or "",
                    source_uri=source_uri or "",
                    content_hash=content_hash_value or "",
                    status=status or "ok",
                    message=message or "",
                    workspace_id=workspace_id or "",
                )
            )
            await session.commit()

    async def list_sync_log(
        self, workspace_id: str = "", limit: int = 40
    ) -> List[Dict[str, Any]]:
        async with self.session_factory() as session:
            stmt = (
                select(KnowledgeSyncLog)
                .order_by(KnowledgeSyncLog.created_at.desc())
                .limit(limit)
            )
            if workspace_id:
                stmt = stmt.where(KnowledgeSyncLog.workspace_id == workspace_id)
            rows = (await session.execute(stmt)).scalars().all()
            return [
                {
                    "id": r.id,
                    "source": r.source,
                    "source_uri": r.source_uri,
                    "content_hash": r.content_hash,
                    "status": r.status,
                    "message": r.message,
                    "workspace_id": r.workspace_id,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ]

    async def latest_sync_hash(
        self,
        *,
        source: str,
        source_uri: str,
        workspace_id: str = "",
        status: str = "ok",
    ) -> Optional[str]:
        """Return content_hash of the newest matching sync log row, if any."""
        async with self.session_factory() as session:
            stmt = (
                select(KnowledgeSyncLog)
                .where(KnowledgeSyncLog.source == (source or ""))
                .where(KnowledgeSyncLog.source_uri == (source_uri or ""))
                .where(KnowledgeSyncLog.status == (status or "ok"))
                .order_by(KnowledgeSyncLog.created_at.desc())
                .limit(1)
            )
            if workspace_id:
                stmt = stmt.where(KnowledgeSyncLog.workspace_id == workspace_id)
            row = (await session.execute(stmt)).scalar_one_or_none()
            if not row:
                return None
            return str(row.content_hash or "") or None

    async def latest_sync_message(
        self,
        *,
        source: str,
        source_uri: str,
        workspace_id: str = "",
        status: str = "ok",
    ) -> Optional[str]:
        """Return message of the newest matching sync log row, if any."""
        async with self.session_factory() as session:
            stmt = (
                select(KnowledgeSyncLog)
                .where(KnowledgeSyncLog.source == (source or ""))
                .where(KnowledgeSyncLog.source_uri == (source_uri or ""))
                .where(KnowledgeSyncLog.status == (status or "ok"))
                .order_by(KnowledgeSyncLog.created_at.desc())
                .limit(1)
            )
            if workspace_id:
                stmt = stmt.where(KnowledgeSyncLog.workspace_id == workspace_id)
            row = (await session.execute(stmt)).scalar_one_or_none()
            if not row:
                return None
            return str(row.message or "") or None

    async def find_sync_uri_by_message(
        self,
        *,
        source: str,
        message: str,
        workspace_id: str = "",
        status: str = "ok",
        source_uri_prefix: str = "",
    ) -> Optional[str]:
        """Newest sync log source_uri whose message matches (e.g. idmap → local doc)."""
        key = (message or "").strip()
        if not key:
            return None
        async with self.session_factory() as session:
            stmt = (
                select(KnowledgeSyncLog)
                .where(KnowledgeSyncLog.source == (source or ""))
                .where(KnowledgeSyncLog.message == key)
                .where(KnowledgeSyncLog.status == (status or "ok"))
                .order_by(KnowledgeSyncLog.created_at.desc())
                .limit(40)
            )
            if workspace_id:
                stmt = stmt.where(KnowledgeSyncLog.workspace_id == workspace_id)
            rows = list((await session.execute(stmt)).scalars().all())
        prefix = (source_uri_prefix or "").strip()
        fallback: Optional[str] = None
        for row in rows:
            uri = str(row.source_uri or "")
            if not uri:
                continue
            if prefix and not uri.startswith(prefix):
                continue
            rest = uri[len(prefix) :] if prefix else uri
            if rest.startswith("titlehash:"):
                fallback = fallback or uri
                continue
            return uri
        return fallback

    @staticmethod
    def _snippet(content: str, tokens: List[str], radius: int = SNIPPET_RADIUS) -> str:
        lower = content.lower()
        idx = -1
        hit = ""
        for t in tokens:
            if not t:
                continue
            i = lower.find(t.lower())
            if i >= 0:
                idx = i
                hit = t
                break
        if idx < 0:
            return (content[: radius * 2] + "…") if len(content) > radius * 2 else content
        start = max(0, idx - radius)
        end = min(len(content), idx + len(hit) + radius)
        piece = content[start:end]
        if start > 0:
            piece = "…" + piece
        if end < len(content):
            piece = piece + "…"
        return piece

    @staticmethod
    def _chunk_public(row: KnowledgeChunk) -> Dict[str, Any]:
        return {
            "chunk_id": row.chunk_id,
            "doc_id": row.doc_id,
            "chunk_index": row.chunk_index,
            "heading": row.heading,
            "context_header": getattr(row, "context_header", "") or "",
            "parent_chunk_id": getattr(row, "parent_chunk_id", "") or "",
            "chunk_type": getattr(row, "chunk_type", "") or "text",
            "content": row.content,
            "char_start": row.char_start,
            "char_end": row.char_end,
            "has_embedding": bool(row.embedding),
            "embedding_model": getattr(row, "embedding_model", "") or "",
            "kb_id": getattr(row, "kb_id", "") or "",
        }

    @staticmethod
    def _public(row: KnowledgeDoc, *, include_content: bool = True) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "doc_id": row.doc_id,
            "title": row.title,
            "tags": row.tags,
            "source": row.source,
            "source_uri": getattr(row, "source_uri", "") or "",
            "content_hash": getattr(row, "content_hash", "") or "",
            "workspace_id": row.workspace_id,
            "kb_id": getattr(row, "kb_id", "") or DEFAULT_LOCAL_KB_ID,
            "parse_status": getattr(row, "parse_status", "") or "completed",
            "parse_error": getattr(row, "parse_error", "") or "",
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
        if include_content:
            out["content"] = row.content
            out["content_len"] = len(row.content or "")
        else:
            out["content_len"] = len(row.content or "")
        return out
