"""Tests for knowledge store chunking, search, citations, sync, ingest."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.core_kernel.plugin_runtime.knowledge_store import (
    Base,
    KnowledgeStore,
    chunk_markdown,
    citations_markdown,
    content_hash,
    format_citation,
    _tokens,
)
from src.infrastructure.storage.database import Base as AppBase


@pytest.fixture
async def store(tmp_path):
    url = f"sqlite+aiosqlite:///{(tmp_path / 'kb.db').as_posix()}"
    engine = create_async_engine(url, future=True)
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
    joined = " ".join(c["content"] for c in chunks)
    assert "alpha" in joined and "beta" in joined


def test_content_hash_stable():
    assert content_hash("hello") == content_hash("hello")
    assert content_hash("hello") != content_hash("world")


def test_tokens_include_cjk_bigrams():
    toks = _tokens("知识库检索 architecture")
    assert "architecture" in toks
    assert any("知识" in t or t == "知识库" for t in toks)


def test_format_citation_and_markdown():
    cite = format_citation(
        title="Guide",
        source="file:docs/guide.md",
        source_uri="docs/guide.md",
        doc_id="file_abc",
        chunk_index=1,
        heading="Intro",
    )
    assert "Guide" in cite and "docs/guide.md" in cite
    md = citations_markdown(
        [{"title": "Guide", "source_uri": "docs/guide.md", "doc_id": "x", "snippet": "hello"}]
    )
    assert "Knowledge references" in md
    assert "Guide" in md


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
    assert hits[0].get("citation")
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
async def test_patch_and_stats(store: KnowledgeStore):
    await store.upsert(
        doc_id="kb_patch",
        title="Old",
        content="# Hello\n\nworld knowledge patch\n",
        workspace_id="ws",
    )
    patched = await store.patch("kb_patch", title="New Title")
    assert patched and patched["title"] == "New Title"
    st = await store.stats(workspace_id="ws")
    assert st["docs"] >= 1
    assert st["chunks"] >= 1
    assert "hybrid_ready" in st


@pytest.mark.asyncio
async def test_hybrid_search_uses_vectors_without_keyword(store: KnowledgeStore, monkeypatch):
    monkeypatch.setenv("KB_EMBEDDING_BASE_URL", "http://embed.test/v1")
    monkeypatch.setenv("KB_EMBEDDING_ENABLED", "1")

    # Fixed 3-d vectors: doc about cats, query about felines (no shared keywords)
    cat_vec = [1.0, 0.0, 0.0]
    query_vec = [0.95, 0.05, 0.0]

    async def fake_embed_texts(texts):
        return [list(cat_vec) for _ in texts]

    async def fake_embed_one(text):
        return list(query_vec)

    with (
        patch(
            "src.core_kernel.plugin_runtime.knowledge_store.embed_texts",
            new=AsyncMock(side_effect=fake_embed_texts),
        ),
        patch(
            "src.core_kernel.plugin_runtime.knowledge_store.embed_one",
            new=AsyncMock(side_effect=fake_embed_one),
        ),
        patch(
            "src.core_kernel.plugin_runtime.knowledge_store.embeddings_configured",
            return_value=True,
        ),
    ):
        await store.upsert(
            doc_id="kb_cat",
            title="Pets",
            content="Cats purr and nap in sunbeams on the windowsill.",
            workspace_id="ws",
        )
        hits = await store.search("feline behavior outdoors", workspace_id="ws", limit=5)
        assert hits
        assert hits[0]["doc_id"] == "kb_cat"
        assert hits[0]["score"] > 0


@pytest.mark.asyncio
async def test_reindex_embeddings(store: KnowledgeStore, monkeypatch):
    monkeypatch.setenv("KB_EMBEDDING_BASE_URL", "http://embed.test/v1")

    await store.upsert(
        doc_id="kb_re",
        title="Re",
        content="# Re\n\nneeds vectors later\n",
        workspace_id="ws",
    )
    # Clear embeddings as if added without embed config
    async with store.session_factory() as session:
        from sqlalchemy import update
        from src.core_kernel.plugin_runtime.knowledge_store import KnowledgeChunk

        await session.execute(
            update(KnowledgeChunk)
            .where(KnowledgeChunk.doc_id == "kb_re")
            .values(embedding="")
        )
        await session.commit()

    async def fake_embed_texts(texts):
        return [[0.1, 0.2, 0.3] for _ in texts]

    with (
        patch(
            "src.core_kernel.plugin_runtime.knowledge_store.embeddings_configured",
            return_value=True,
        ),
        patch(
            "src.core_kernel.plugin_runtime.knowledge_store.embed_texts",
            new=AsyncMock(side_effect=fake_embed_texts),
        ),
    ):
        result = await store.reindex_embeddings(workspace_id="ws", limit=50)
        assert result["ok"] is True
        assert result["updated"] >= 1

    full = await store.get("kb_re", include_chunks=True)
    assert full and full["chunks"][0]["has_embedding"] is True


@pytest.mark.asyncio
async def test_sync_workspace_docs(tmp_path, store: KnowledgeStore):
    from src.core_kernel.plugin_runtime.knowledge_sync import sync_workspace_docs

    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "guide.md").write_text("# Guide\n\nhello knowledge sync\n", encoding="utf-8")
    (docs / "notes.txt").write_text("plain text knowledge note\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Readme\n\nroot md\n", encoding="utf-8")

    result = await sync_workspace_docs(store, str(tmp_path), workspace_id="ws")
    assert result["ok"] is True
    assert result["scanned"] >= 3
    assert result["added"] >= 1

    hits = await store.search("knowledge sync", workspace_id="ws", limit=5)
    assert any(h["doc_id"].startswith("file_") for h in hits)

    again = await sync_workspace_docs(store, str(tmp_path), workspace_id="ws")
    assert again["skipped"] >= 1


def test_ingest_txt_and_crude_pdf(tmp_path):
    from src.core_kernel.plugin_runtime.knowledge_ingest import read_file_as_text

    p = tmp_path / "a.txt"
    p.write_text("hello txt", encoding="utf-8")
    text, note = read_file_as_text(p)
    assert text == "hello txt"
    assert note == ""

    # Minimal PDF-like bytes with a literal string
    pdf = tmp_path / "b.pdf"
    pdf.write_bytes(b"%PDF-1.4\nBT (HelloPDFWorld) Tj ET\n%%EOF")
    text2, note2 = read_file_as_text(pdf)
    assert "HelloPDFWorld" in text2
    assert note2


@pytest.mark.asyncio
async def test_weknora_client_skipped_without_env(monkeypatch):
    from src.core_kernel.plugin_runtime.weknora_client import weknora_search

    monkeypatch.delenv("WEKNORA_BASE_URL", raising=False)
    out = await weknora_search("test")
    assert out["skipped"] is True
    assert out["results"] == []


def test_weknora_cli_skipped(monkeypatch, capsys):
    monkeypatch.delenv("WEKNORA_BASE_URL", raising=False)
    import importlib.util
    import sys
    from io import StringIO
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "plugins_volume" / "cli" / "weknora_search.py"
    spec = importlib.util.spec_from_file_location("weknora_search_cli", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(sys, "stdin", StringIO(json.dumps({"query": "x"})))
    code = mod.main()
    assert code == 0
    captured = capsys.readouterr().out
    data = json.loads(captured)
    assert data.get("skipped") is True
