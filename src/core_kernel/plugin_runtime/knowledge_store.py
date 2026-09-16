"""Local SQLite knowledge base — chunked keyword + optional hybrid vector search."""

from __future__ import annotations

import hashlib
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
    embed_texts,
    embeddings_configured,
    serialize_embedding,
)
from src.infrastructure.storage.database import Base

CHUNK_TARGET = 512
CHUNK_OVERLAP_RATIO = 0.15
SNIPPET_RADIUS = 160


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


def _tokens(q: str) -> List[str]:
    parts = re.split(r"[\s,;|/]+", (q or "").strip().lower())
    return [p for p in parts if len(p) >= 2][:12]


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
    blocks: List[Tuple[str, str, int]] = []  # heading, text, start
    heading = ""
    buf: List[str] = []
    start = 0
    pos = 0
    lines = text_body.splitlines(keepends=True)
    for line in lines:
        if re.match(r"^#{1,6}\s+\S", line):
            if buf:
                piece = "".join(buf)
                blocks.append((heading, piece, start))
                buf = []
            heading = line.lstrip("#").strip()
            start = pos
            buf.append(line)
        else:
            if not buf:
                start = pos
            buf.append(line)
            # flush oversized paragraph runs on blank lines
            if line.strip() == "" and sum(len(x) for x in buf) >= target:
                piece = "".join(buf)
                blocks.append((heading, piece, start))
                buf = []
                heading = heading  # keep section heading
        pos += len(line)
    if buf:
        blocks.append((heading, "".join(buf), start))

    # Re-pack blocks into target-sized chunks with overlap
    overlap = max(32, int(target * overlap_ratio))
    chunks: List[Dict[str, Any]] = []
    carry = ""
    carry_heading = ""
    carry_start = 0
    for h, piece, st in blocks:
        section = piece
        sec_heading = h or carry_heading
        sec_start = st
        if carry:
            section = carry + section
            sec_heading = carry_heading or h
            sec_start = carry_start
            carry = ""
        while len(section) > target:
            cut = _soft_cut(section, target)
            chunk_text = section[:cut].rstrip()
            if chunk_text:
                chunks.append(
                    {
                        "heading": sec_heading,
                        "content": chunk_text,
                        "char_start": sec_start,
                        "char_end": sec_start + len(chunk_text),
                    }
                )
            # overlap window
            back = min(overlap, len(chunk_text))
            next_start_off = max(0, cut - back)
            sec_start = sec_start + next_start_off
            section = section[next_start_off:]
        carry = section
        carry_heading = sec_heading
        carry_start = sec_start
    if carry.strip():
        chunks.append(
            {
                "heading": carry_heading,
                "content": carry.rstrip(),
                "char_start": carry_start,
                "char_end": carry_start + len(carry.rstrip()),
            }
        )
    if not chunks and text_body.strip():
        chunks.append(
            {
                "heading": "",
                "content": text_body.strip(),
                "char_start": 0,
                "char_end": len(text_body.strip()),
            }
        )
    return chunks


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

    async def ensure_schema(self) -> None:
        from src.infrastructure.storage.database import get_engine

        try:
            engine = get_engine()
        except Exception:
            return
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            # Lightweight column adds for existing SQLite DBs
            for ddl in (
                "ALTER TABLE knowledge_docs ADD COLUMN source_uri VARCHAR(1024) DEFAULT ''",
                "ALTER TABLE knowledge_docs ADD COLUMN content_hash VARCHAR(64) DEFAULT ''",
            ):
                try:
                    await conn.execute(text(ddl))
                except Exception:
                    pass

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
            pieces = chunk_markdown(body)
            emb_vectors: Optional[List[Optional[List[float]]]] = None
            if embeddings_configured() and pieces:
                raw = await embed_texts([p["content"] for p in pieces])
                if raw:
                    emb_vectors = raw

            for i, piece in enumerate(pieces):
                emb_json = ""
                if emb_vectors and i < len(emb_vectors) and emb_vectors[i]:
                    emb_json = serialize_embedding(emb_vectors[i])  # type: ignore[arg-type]
                session.add(
                    KnowledgeChunk(
                        chunk_id=f"{doc_id}#{i}",
                        doc_id=doc_id,
                        chunk_index=i,
                        heading=str(piece.get("heading") or "")[:512],
                        content=str(piece.get("content") or ""),
                        char_start=int(piece.get("char_start") or 0),
                        char_end=int(piece.get("char_end") or 0),
                        embedding=emb_json,
                        workspace_id=row.workspace_id,
                        updated_at=datetime.now(timezone.utc),
                    )
                )
            await session.commit()
            return self._public(row)

    async def delete(self, doc_id: str) -> bool:
        async with self.session_factory() as session:
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

    async def list_docs(self, workspace_id: str = "", limit: int = 50) -> List[Dict[str, Any]]:
        async with self.session_factory() as session:
            stmt = select(KnowledgeDoc).order_by(KnowledgeDoc.updated_at.desc()).limit(limit)
            if workspace_id:
                stmt = stmt.where(
                    or_(KnowledgeDoc.workspace_id == workspace_id, KnowledgeDoc.workspace_id == "")
                )
            rows = (await session.execute(stmt)).scalars().all()
            return [self._public(r, include_content=False) for r in rows]

    async def search(
        self, query: str, *, workspace_id: str = "", limit: int = 8
    ) -> List[Dict[str, Any]]:
        tokens = _tokens(query)
        q = (query or "").strip()
        async with self.session_factory() as session:
            # Prefer chunk hits; fall back to whole-doc if no chunks yet
            stmt = select(KnowledgeChunk)
            if workspace_id:
                stmt = stmt.where(
                    or_(
                        KnowledgeChunk.workspace_id == workspace_id,
                        KnowledgeChunk.workspace_id == "",
                    )
                )
            likes = []
            if q:
                likes.append(KnowledgeChunk.content.ilike(f"%{q}%"))
                likes.append(KnowledgeChunk.heading.ilike(f"%{q}%"))
            for t in tokens:
                likes.append(KnowledgeChunk.content.ilike(f"%{t}%"))
                likes.append(KnowledgeChunk.heading.ilike(f"%{t}%"))
            if likes:
                stmt = stmt.where(or_(*likes))
            stmt = stmt.limit(120)
            chunks = list((await session.execute(stmt)).scalars().all())

            doc_ids = {c.doc_id for c in chunks}
            docs_by_id: Dict[str, KnowledgeDoc] = {}
            if doc_ids:
                drows = (
                    await session.execute(
                        select(KnowledgeDoc).where(KnowledgeDoc.doc_id.in_(list(doc_ids)))
                    )
                ).scalars().all()
                docs_by_id = {d.doc_id: d for d in drows}

            # If no chunks matched, fall back to document-level search (legacy rows)
            if not chunks:
                return await self._search_docs(session, query, tokens, workspace_id, limit)

        query_vec: Optional[List[float]] = None
        if embeddings_configured() and q:
            query_vec = await embed_one(q)

        scored: List[Tuple[float, KnowledgeChunk, KnowledgeDoc]] = []
        for c in chunks:
            doc = docs_by_id.get(c.doc_id)
            if not doc:
                continue
            kw = _score_text(
                f"{c.heading}\n{c.content}",
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
            if total <= 0 and tokens and not query_vec:
                continue
            scored.append((total, c, doc))

        scored.sort(key=lambda x: x[0], reverse=True)
        out: List[Dict[str, Any]] = []
        seen_docs: set[str] = set()
        for sc, c, doc in scored:
            # Prefer diverse docs but allow multiple chunks if room
            if doc.doc_id in seen_docs and len(out) >= max(2, limit // 2):
                continue
            seen_docs.add(doc.doc_id)
            item = {
                "doc_id": doc.doc_id,
                "chunk_id": c.chunk_id,
                "chunk_index": c.chunk_index,
                "title": doc.title,
                "heading": c.heading,
                "tags": doc.tags,
                "source": doc.source,
                "source_uri": getattr(doc, "source_uri", "") or "",
                "workspace_id": doc.workspace_id,
                "score": round(sc, 3),
                "snippet": self._snippet(c.content or "", tokens or [query]),
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
            out.append(item)
        return out

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
