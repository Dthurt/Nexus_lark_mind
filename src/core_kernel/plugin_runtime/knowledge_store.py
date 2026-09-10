"""Local SQLite knowledge base — text / LIKE / approximate token search (no vectors)."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import DateTime, Integer, String, Text, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.storage.database import Base


class KnowledgeDoc(Base):
    __tablename__ = "knowledge_docs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doc_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(512), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[str] = mapped_column(String(512), default="")  # comma-separated
    source: Mapped[str] = mapped_column(String(256), default="")
    workspace_id: Mapped[str] = mapped_column(String(128), default="", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


def _tokens(q: str) -> List[str]:
    parts = re.split(r"[\s,;|/]+", (q or "").strip().lower())
    return [p for p in parts if len(p) >= 2][:12]


def _score(doc: KnowledgeDoc, tokens: List[str], query: str) -> float:
    blob = f"{doc.title}\n{doc.tags}\n{doc.content}".lower()
    if not blob:
        return 0.0
    score = 0.0
    q = (query or "").lower().strip()
    if q and q in blob:
        score += 5.0
    for t in tokens:
        if t in (doc.title or "").lower():
            score += 2.0
        if t in (doc.tags or "").lower():
            score += 1.5
        score += min(3.0, blob.count(t) * 0.35)
    return score


class KnowledgeStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def ensure_schema(self) -> None:
        # create_all already runs on boot; keep for safety if manager loads later
        from src.infrastructure.storage.database import get_engine

        try:
            engine = get_engine()
        except Exception:
            return
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def upsert(
        self,
        *,
        doc_id: str,
        title: str,
        content: str,
        tags: str = "",
        source: str = "",
        workspace_id: str = "",
    ) -> Dict[str, Any]:
        async with self.session_factory() as session:
            row = (
                await session.execute(select(KnowledgeDoc).where(KnowledgeDoc.doc_id == doc_id))
            ).scalar_one_or_none()
            if row is None:
                row = KnowledgeDoc(doc_id=doc_id)
                session.add(row)
            row.title = title or row.title or doc_id
            row.content = content or ""
            row.tags = tags or ""
            row.source = source or ""
            row.workspace_id = workspace_id or ""
            row.updated_at = datetime.now(timezone.utc)
            await session.commit()
            return self._public(row)

    async def delete(self, doc_id: str) -> bool:
        async with self.session_factory() as session:
            res = await session.execute(delete(KnowledgeDoc).where(KnowledgeDoc.doc_id == doc_id))
            await session.commit()
            return (res.rowcount or 0) > 0

    async def get(self, doc_id: str) -> Optional[Dict[str, Any]]:
        async with self.session_factory() as session:
            row = (
                await session.execute(select(KnowledgeDoc).where(KnowledgeDoc.doc_id == doc_id))
            ).scalar_one_or_none()
            return self._public(row) if row else None

    async def list_docs(self, workspace_id: str = "", limit: int = 50) -> List[Dict[str, Any]]:
        async with self.session_factory() as session:
            stmt = select(KnowledgeDoc).order_by(KnowledgeDoc.updated_at.desc()).limit(limit)
            if workspace_id:
                stmt = stmt.where(
                    or_(KnowledgeDoc.workspace_id == workspace_id, KnowledgeDoc.workspace_id == "")
                )
            rows = (await session.execute(stmt)).scalars().all()
            return [self._public(r) for r in rows]

    async def search(
        self, query: str, *, workspace_id: str = "", limit: int = 8
    ) -> List[Dict[str, Any]]:
        tokens = _tokens(query)
        async with self.session_factory() as session:
            stmt = select(KnowledgeDoc)
            if workspace_id:
                stmt = stmt.where(
                    or_(KnowledgeDoc.workspace_id == workspace_id, KnowledgeDoc.workspace_id == "")
                )
            # Prefilter with SQL LIKE on any token / full query
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
        scored = [( _score(r, tokens, query), r) for r in rows]
        scored.sort(key=lambda x: x[0], reverse=True)
        out = []
        for sc, r in scored[:limit]:
            if sc <= 0 and tokens:
                continue
            item = self._public(r)
            item["score"] = round(sc, 3)
            item["snippet"] = self._snippet(r.content or "", tokens or [query])
            out.append(item)
        return out

    @staticmethod
    def _snippet(content: str, tokens: List[str], radius: int = 90) -> str:
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
    def _public(row: KnowledgeDoc) -> Dict[str, Any]:
        return {
            "doc_id": row.doc_id,
            "title": row.title,
            "content": row.content,
            "tags": row.tags,
            "source": row.source,
            "workspace_id": row.workspace_id,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
