"""Local SQLite knowledge base — chunked keyword + optional hybrid vector search."""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
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
    embed_one,
    embed_one_image,
    embed_texts,
    embeddings_configured,
    embedding_stats,
    multimodal_embeddings_enabled,
    serialize_embedding,
)
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
    parent_chunk_id: Mapped[str] = mapped_column(String(80), default="", index=True)
    chunk_type: Mapped[str] = mapped_column(String(32), default="text")  # text|parent|image
    context_header: Mapped[str] = mapped_column(String(1024), default="")
    workspace_id: Mapped[str] = mapped_column(String(128), default="", index=True)
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


def format_citation(
    *,
    title: str,
    source: str = "",
    source_uri: str = "",
    doc_id: str = "",
    chunk_index: Optional[int] = None,
    heading: str = "",
    context_header: str = "",
) -> str:
    """Human-readable provenance line for chat / tool results."""
    label = (title or doc_id or "untitled").strip()
    path = (source_uri or "").strip()
    if not path and (source or "").startswith("file:"):
        path = source[5:]
    section = (context_header or heading or "").strip()
    if section:
        section = re.sub(r"^#+\s*", "", section.replace("\n", " › "))
    parts = [f"**{label}**"]
    if path:
        parts.append(f"`{path}`")
    elif source:
        parts.append(f"({source})")
    if section:
        parts.append(f"§ {section}")
    if chunk_index is not None:
        parts.append(f"chunk #{chunk_index}")
    if doc_id:
        parts.append(f"[{doc_id}]")
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


def parent_child_enabled() -> bool:
    import os

    v = (os.getenv("KB_PARENT_CHILD") or "1").strip().lower()
    return v not in {"0", "false", "no", "off"}


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


def split_document(content: str) -> List[Dict[str, Any]]:
    if parent_child_enabled() and len(content or "") > PARENT_CHUNK_TARGET // 2:
        return chunk_parent_child(content)
    return chunk_markdown(content)


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
            "ALTER TABLE knowledge_chunks ADD COLUMN parent_chunk_id VARCHAR(80) DEFAULT ''",
            "ALTER TABLE knowledge_chunks ADD COLUMN chunk_type VARCHAR(32) DEFAULT 'text'",
            "ALTER TABLE knowledge_chunks ADD COLUMN context_header VARCHAR(1024) DEFAULT ''",
        ):
            try:
                async with self.session_factory() as session:
                    await session.execute(text(ddl))
                    await session.commit()
            except Exception:
                pass
        async with self.session_factory() as session:
            conn = await session.connection()
            self._fts_mode = await self._ensure_fts(conn)
            await session.commit()

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
        content_hash_value: Optional[str] = None,
        skip_if_unchanged: bool = False,
    ) -> Dict[str, Any]:
        body = content or ""
        digest = content_hash_value or content_hash(body)
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
            row.updated_at = datetime.now(timezone.utc)
            await session.flush()

            await session.execute(delete(KnowledgeChunk).where(KnowledgeChunk.doc_id == doc_id))
            pieces = split_document(body)
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
            if embeddings_configured() and embeddable:
                raw = await embed_texts([chunk_embedding_text(p) for _, p in embeddable])
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
                        parent_chunk_id=parent_id[:80],
                        chunk_type=ctype[:32],
                        workspace_id=row.workspace_id,
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
        self, workspace_id: str = "", limit: int = 50, *, tag: str = ""
    ) -> List[Dict[str, Any]]:
        async with self.session_factory() as session:
            stmt = select(KnowledgeDoc).order_by(KnowledgeDoc.updated_at.desc()).limit(limit)
            if workspace_id:
                stmt = stmt.where(
                    or_(KnowledgeDoc.workspace_id == workspace_id, KnowledgeDoc.workspace_id == "")
                )
            tag_s = (tag or "").strip()
            if tag_s:
                stmt = stmt.where(KnowledgeDoc.tags.ilike(f"%{tag_s}%"))
            if not tag_s.startswith("session:"):
                stmt = stmt.where(KnowledgeDoc.source != "session-upload")
            rows = (await session.execute(stmt)).scalars().all()
            return [self._public(r, include_content=False) for r in rows]

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
            q, workspace_id=workspace_id, limit=pool, tag=tag, session_id=session_id
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
    ) -> List[Dict[str, Any]]:
        tokens = _tokens(query)
        q = (query or "").strip()
        use_vec = embeddings_configured() and bool(q) and not skip_vector
        if use_vec and query_vec is None:
            query_vec = await embed_one(q)

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
                if ws_filter is not None:
                    vstmt = vstmt.where(ws_filter)
                vstmt = vstmt.order_by(KnowledgeChunk.updated_at.desc()).limit(400)
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
                    session, query, tokens, workspace_id, limit, session_id=session_id
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
            )
            display = c.content or ""
            parent = parents_by_id.get(getattr(c, "parent_chunk_id", "") or "")
            if parent and parent.content and len(display) < SHORT_CHUNK_EXPAND:
                display = parent.content
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
                "score": round(sc, 3),
                "snippet": self._snippet(display, tokens or [query]),
                "citation": cite,
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
    ) -> List[Dict[str, Any]]:
        stmt = select(KnowledgeDoc)
        if workspace_id:
            stmt = stmt.where(
                or_(KnowledgeDoc.workspace_id == workspace_id, KnowledgeDoc.workspace_id == "")
            )
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
            item["snippet"] = self._snippet(r.content or "", tokens or [query])
            item["doc_id"] = r.doc_id
            item["citation"] = format_citation(
                title=r.title or "",
                source=r.source or "",
                source_uri=getattr(r, "source_uri", "") or "",
                doc_id=r.doc_id,
            )
            out.append(item)
        return out

    async def stats(self, workspace_id: str = "") -> Dict[str, Any]:
        async with self.session_factory() as session:
            doc_stmt = select(func.count()).select_from(KnowledgeDoc)
            chunk_stmt = select(func.count()).select_from(KnowledgeChunk)
            emb_stmt = (
                select(func.count())
                .select_from(KnowledgeChunk)
                .where(KnowledgeChunk.embedding != "")
            )
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
            docs = int((await session.execute(doc_stmt)).scalar() or 0)
            chunks = int((await session.execute(chunk_stmt)).scalar() or 0)
            embedded = int((await session.execute(emb_stmt)).scalar() or 0)
        info = embedding_stats()
        return {
            "docs": docs,
            "chunks": chunks,
            "chunks_with_embedding": embedded,
            "embeddings_configured": bool(info.get("configured")),
            "embedding_backend": info.get("backend") or "",
            "embedding_model": info.get("model") or "",
            "embedding_dim": info.get("dim") or 0,
            "embedding_multimodal": bool(info.get("multimodal")),
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
            content_hash_value=content_hash(str(new_content)),
            skip_if_unchanged=False,
        )

    async def reindex_embeddings(
        self, *, workspace_id: str = "", limit: int = 200
    ) -> Dict[str, Any]:
        """Embed chunks missing vectors when KB_EMBEDDING_* is configured."""
        if not embeddings_configured():
            return {
                "ok": False,
                "error": "embeddings not configured (set KB_EMBEDDING_BASE_URL)",
                "updated": 0,
            }
        async with self.session_factory() as session:
            stmt = (
                select(KnowledgeChunk)
                .where(
                    or_(KnowledgeChunk.embedding == "", KnowledgeChunk.embedding.is_(None))
                )
                .order_by(KnowledgeChunk.updated_at.desc())
                .limit(max(1, min(limit, 500)))
            )
            if workspace_id:
                stmt = stmt.where(
                    or_(
                        KnowledgeChunk.workspace_id == workspace_id,
                        KnowledgeChunk.workspace_id == "",
                    )
                )
            rows = list((await session.execute(stmt)).scalars().all())
            if not rows:
                return {"ok": True, "updated": 0, "scanned": 0}

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
                vectors = await embed_texts(batch_texts)
                if not vectors:
                    errors.append(f"embed batch@{i} failed")
                    continue
                for row, vec in zip(batch_rows, vectors):
                    if not vec:
                        continue
                    row.embedding = serialize_embedding(vec)
                    row.updated_at = datetime.now(timezone.utc)
                    updated += 1
            await session.commit()
        return {
            "ok": True,
            "scanned": len(rows),
            "updated": updated,
            "errors": errors[:10],
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
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
        if include_content:
            out["content"] = row.content
            out["content_len"] = len(row.content or "")
        else:
            out["content_len"] = len(row.content or "")
        return out
