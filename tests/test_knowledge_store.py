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
    chunk_parent_child,
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


def test_chunk_markdown_keeps_heading_breadcrumb():
    md = "# Chapter\n\nintro para\n\n## Section\n\n" + ("body " * 40)
    chunks = chunk_markdown(md, target=180, overlap_ratio=0.15)
    assert chunks
    headers = " ".join(c.get("context_header") or "" for c in chunks)
    assert "Chapter" in headers
    assert any("Section" in (c.get("context_header") or "") for c in chunks)


def test_chunk_parent_child_search_children():
    md = "# Manual\n\n" + "\n\n".join(
        f"## Part {i}\n\n" + ("detail word " * 80) for i in range(6)
    )
    pieces = chunk_parent_child(md, parent_size=900, child_size=220)
    types = [p.get("chunk_type") for p in pieces]
    assert "parent" in types
    assert types.count("text") >= 2
    children = [p for p in pieces if p.get("chunk_type") != "parent"]
    assert any(int(p.get("parent_index", -1)) >= 0 for p in children)


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
    assert "](/knowledge/" in cite and "/docs/file_abc" in cite and "#c1" in cite
    assert "`doc:file_abc`" in cite
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
    assert "fts5" in st


@pytest.mark.asyncio
async def test_fts5_search_and_delete(store: KnowledgeStore):
    await store.upsert(
        doc_id="kb_fts_en",
        title="Hybrid search",
        content="Adapters orchestrator kernel FTS5 retrieval marker unique_nlm_fts_token.",
        workspace_id="ws",
    )
    await store.upsert(
        doc_id="kb_fts_zh",
        title="知识检索",
        content="本地知识库使用 SQLite 做中文子串检索 unique_cjk_fts_token。",
        workspace_id="ws",
    )
    st = await store.stats()
    hits_en = await store.search("unique_nlm_fts_token", workspace_id="ws", limit=5)
    assert hits_en
    assert hits_en[0]["doc_id"] == "kb_fts_en"
    hits_zh = await store.search("unique_cjk_fts_token", workspace_id="ws", limit=5)
    assert hits_zh
    assert hits_zh[0]["doc_id"] == "kb_fts_zh"
    assert await store.delete("kb_fts_en")
    gone = await store.search("unique_nlm_fts_token", workspace_id="ws", limit=5)
    assert all(h["doc_id"] != "kb_fts_en" for h in gone)


@pytest.mark.asyncio
async def test_session_upload_isolated(store: KnowledgeStore):
    await store.upsert(
        doc_id="upl_a",
        title="Secret A",
        content="session alpha unique_upload_alpha",
        tags="session-upload,session:sA",
        source="session-upload",
        workspace_id="ws",
    )
    await store.upsert(
        doc_id="upl_b",
        title="Secret B",
        content="session beta unique_upload_alpha",
        tags="session-upload,session:sB",
        source="session-upload",
        workspace_id="ws",
    )
    listed = await store.list_docs(workspace_id="ws")
    assert all(d["doc_id"] not in {"upl_a", "upl_b"} for d in listed)
    tagged = await store.list_docs(tag="session:sA")
    assert any(d["doc_id"] == "upl_a" for d in tagged)
    hits_a = await store.search("unique_upload_alpha", workspace_id="ws", session_id="sA")
    assert hits_a
    assert all(h["doc_id"] != "upl_b" for h in hits_a)
    hits_none = await store.search("unique_upload_alpha", workspace_id="ws")
    assert all(h.get("source") != "session-upload" for h in hits_none)


def test_row_visible_for_session_helper():
    from src.core_kernel.plugin_runtime.knowledge_store import row_visible_for_session

    assert row_visible_for_session({"source": "manual", "tags": ""}, "") is True
    row = {"source": "session-upload", "tags": "session-upload,session:sA"}
    assert row_visible_for_session(row, "sA") is True
    assert row_visible_for_session(row, "sB") is False
    assert row_visible_for_session(row, "") is False


@pytest.mark.asyncio
async def test_fts5_backfill_existing_chunks(store: KnowledgeStore):
    from sqlalchemy import text

    await store.upsert(
        doc_id="kb_fts_old",
        title="Legacy",
        content="preexisting unique_fts_backfill_token in the local store.",
        workspace_id="ws",
    )
    if not store._fts_mode:
        return
    async with store.session_factory() as session:
        await session.execute(text("DELETE FROM knowledge_chunks_fts"))
        await session.commit()
    async with store.session_factory() as session:
        conn = await session.connection()
        await store._backfill_fts_if_empty(conn)
        await session.commit()
    hits = await store.search("unique_fts_backfill_token", workspace_id="ws", limit=5)
    assert hits
    assert hits[0]["doc_id"] == "kb_fts_old"


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


@pytest.mark.asyncio
async def test_parent_child_search_expands_short_child(store: KnowledgeStore, monkeypatch):
    monkeypatch.setenv("KB_PARENT_CHILD", "1")
    body = "# Spec\n\n" + "\n\n".join(
        f"## Topic {i}\n\n" + ("uniquephrase " * 60) + f" marker{i}\n"
        for i in range(5)
    )
    await store.upsert(
        doc_id="kb_pc",
        title="Spec",
        content=body,
        workspace_id="ws",
    )
    full = await store.get("kb_pc", include_chunks=True)
    assert full and any(c.get("chunk_type") == "parent" for c in full["chunks"])
    hits = await store.search("uniquephrase marker2", workspace_id="ws", limit=5)
    assert hits
    assert hits[0].get("context_header") or hits[0].get("heading")


def test_ingest_image_placeholder(tmp_path):
    from src.core_kernel.plugin_runtime.knowledge_ingest import read_file_as_text

    img = tmp_path / "shot.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 8)
    text, note = read_file_as_text(img)
    assert "shot.png" in text
    assert note == "image-placeholder"


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


def test_read_bytes_as_text_matches_file():
    from src.core_kernel.plugin_runtime.knowledge_ingest import read_bytes_as_text

    text, note = read_bytes_as_text("# Hello\n".encode("utf-8"), ".md", filename="n.md")
    assert "Hello" in text
    assert note == ""
    img, n2 = read_bytes_as_text(b"\x89PNG", ".png", filename="x.png")
    assert "x.png" in img
    assert n2 == "image-placeholder"
    text2, note2 = read_file_as_text(pdf)
    assert "HelloPDFWorld" in text2
    assert note2


def test_read_bytes_as_text_matches_file():
    from src.core_kernel.plugin_runtime.knowledge_ingest import read_bytes_as_text

    text, note = read_bytes_as_text("# Hello\n".encode("utf-8"), ".md", filename="n.md")
    assert "Hello" in text
    assert note == ""
    img, n2 = read_bytes_as_text(b"\x89PNG", ".png", filename="x.png")
    assert "x.png" in img
    assert n2 == "image-placeholder"


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
