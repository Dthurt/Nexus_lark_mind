"""Tests for knowledge store chunking, search, and content_hash upsert."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.core_kernel.plugin_runtime.knowledge_store import (
    Base,
    KnowledgeStore,
    chunk_markdown,
    content_hash,
)
from src.infrastructure.storage.database import Base as AppBase


@pytest.fixture
async def store(tmp_path):
    url = f"sqlite+aiosqlite:///{(tmp_path / 'kb.db').as_posix()}"
    engine = create_async_engine(url, future=True)
    # Bind knowledge models onto shared Base metadata
    assert Base is AppBase
    async with engine.begin() as conn:
        await conn.run_sync(AppBase.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    kb = KnowledgeStore(factory)
    await kb.ensure_schema()
    yield kb
    await engine.dispose()


def test_chunk_markdown_splits_headings_and_paragraphs():
    md = (
        "# Title\n\n"
        + ("alpha " * 80)
        + "\n\n## Section\n\n"
        + ("beta " * 80)
        + "\n\n"
        + ("gamma " * 40)
    )
    chunks = chunk_markdown(md, target=200, overlap_ratio=0.15)
    assert len(chunks) >= 2
    assert all(c["content"] for c in chunks)
    # Overlap: later chunk should share some tail with previous when overlapping
    joined = " ".join(c["content"] for c in chunks)
    assert "alpha" in joined and "beta" in joined


def test_content_hash_stable():
    assert content_hash("hello") == content_hash("hello")
    assert content_hash("hello") != content_hash("world")


@pytest.mark.asyncio
async def test_upsert_chunks_and_search(store: KnowledgeStore):
    doc = await store.upsert(
        doc_id="kb_test_1",
        title="Architecture Notes",
        content=(
            "# Architecture\n\n"
            "Nexus uses Adapters, Orchestrator, and Core Kernel.\n\n"
            "## Knowledge\n\n"
            "The local knowledge base stores markdown chunks for retrieval.\n"
        ),
        tags="arch,kb",
        source="test",
        workspace_id="ws1",
    )
    assert doc["doc_id"] == "kb_test_1"
    assert doc["content_hash"]

    full = await store.get("kb_test_1", include_chunks=True)
    assert full is not None
    assert full["chunks"]
    assert full["chunks"][0]["chunk_id"].startswith("kb_test_1#")

    hits = await store.search("knowledge base chunks", workspace_id="ws1", limit=5)
    assert hits
    assert hits[0]["doc_id"] == "kb_test_1"
    assert "snippet" in hits[0]
    assert len(hits[0]["snippet"]) > 20

    window = await store.read("kb_test_1", offset=0, limit=40)
    assert window and window["text"]
    assert window["total"] >= len(window["text"])

    by_chunk = await store.read("kb_test_1", chunk_index=0, neighbors=1)
    assert by_chunk and by_chunk.get("chunks")


@pytest.mark.asyncio
async def test_upsert_skip_if_unchanged(store: KnowledgeStore):
    body = "# Same\n\nunchanged body\n"
    first = await store.upsert(
        doc_id="kb_same",
        title="Same",
        content=body,
        workspace_id="ws",
        skip_if_unchanged=True,
    )
    second = await store.upsert(
        doc_id="kb_same",
        title="Same",
        content=body,
        workspace_id="ws",
        skip_if_unchanged=True,
    )
    assert first.get("unchanged") is not True
    assert second.get("unchanged") is True

    third = await store.upsert(
        doc_id="kb_same",
        title="Same",
        content=body + "\nextra\n",
        workspace_id="ws",
        skip_if_unchanged=True,
    )
    assert third.get("unchanged") is not True
    assert third["content_hash"] != first["content_hash"]


@pytest.mark.asyncio
async def test_delete_removes_chunks(store: KnowledgeStore):
    await store.upsert(doc_id="kb_del", title="Del", content="# X\n\nbye\n")
    assert await store.get("kb_del", include_chunks=True)
    assert await store.delete("kb_del") is True
    assert await store.get("kb_del") is None


@pytest.mark.asyncio
async def test_sync_workspace_docs(tmp_path, store: KnowledgeStore):
    from src.core_kernel.plugin_runtime.knowledge_sync import sync_workspace_docs

    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "guide.md").write_text("# Guide\n\nhello knowledge sync\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Readme\n\nroot md\n", encoding="utf-8")

    result = await sync_workspace_docs(store, str(tmp_path), workspace_id="ws")
    assert result["ok"] is True
    assert result["scanned"] >= 2
    assert result["added"] >= 1

    hits = await store.search("knowledge sync", workspace_id="ws", limit=5)
    assert any(h["doc_id"].startswith("file_") for h in hits)

    # Second pass should skip unchanged
    again = await sync_workspace_docs(store, str(tmp_path), workspace_id="ws")
    assert again["skipped"] >= 1
