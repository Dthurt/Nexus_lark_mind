"""Wiki distill, revisions, conflict, graph, and wiki search citations."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.core_kernel.kb_grounding import retrieve_bound_knowledge
from src.core_kernel.knowledge_rpc import register_knowledge_rpc
from src.core_kernel.plugin_runtime.knowledge_store import (
    Base,
    KnowledgeStore,
    format_citation,
)
from src.core_kernel.plugin_runtime.knowledge_wiki import (
    apply_distill,
    parse_wikilinks,
    rule_distill_doc,
    slugify,
)
from src.infrastructure.storage.database import Base as AppBase


@pytest.fixture
async def store(tmp_path):
    url = f"sqlite+aiosqlite:///{(tmp_path / 'wiki.db').as_posix()}"
    engine = create_async_engine(url, future=True)
    assert Base is AppBase
    async with engine.begin() as conn:
        await conn.run_sync(AppBase.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    kb = KnowledgeStore(factory)
    await kb.ensure_schema()
    yield kb
    await engine.dispose()


def test_slugify_and_wikilinks():
    assert slugify("Hello World") == "hello-world"
    assert slugify("产品文档") == "产品文档"
    links = parse_wikilinks("See [[Other]] and [[slug|Label]] plus [[doc:abc|原文]]")
    kinds = {(x["to_kind"], x["to_id"]) for x in links}
    assert ("page", "other") in kinds
    assert ("page", "slug") in kinds
    assert ("doc", "abc") in kinds


def test_wiki_citation_prefix():
    cite = format_citation(
        title="概述",
        source="wiki",
        source_uri="wiki:_index",
        doc_id="wiki:wpg_1",
    )
    assert "wiki:_index" in cite
    assert "](/knowledge/" in cite and "/wiki/_index" in cite


@pytest.mark.asyncio
async def test_rule_distill_crud_conflict_rollback_and_search(store: KnowledgeStore, monkeypatch):
    monkeypatch.delenv("GLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("KB_WIKI", "1")
    kb_id = "local:default"
    docs = []
    for i, title in enumerate(("Alpha Notes", "Beta Guide", "Gamma Spec"), 1):
        row = await store.upsert(
            doc_id=f"doc_{i}",
            title=title,
            content=f"# {title}\n\nMarker wiki_{title.split()[0].lower()} body.\n\n## Detail\n\nMore text.",
            source="test",
            kb_id=kb_id,
        )
        docs.append(row)

    bundle = {
        "mode": "rules",
        "pages": [rule_distill_doc(d) for d in docs],
        "entities": [],
        "triples": [],
    }
    result = await apply_distill(store, kb_id=kb_id, workspace_id="", bundle=bundle)
    slugs = {p["slug"] for p in result["pages"]}
    assert "alpha-notes" in slugs
    assert "_index" in slugs
    assert not result["conflicts"]

    page = await store.get_wiki_page(kb_id, "alpha-notes")
    assert page and "wiki_alpha" in (page.get("content") or "")
    assert page["revisions"]

    edited = await store.save_wiki_page(
        kb_id=kb_id,
        slug="alpha-notes",
        title="Alpha Notes",
        content="# Alpha Notes\n\nUser rewrite keeps this phrase unique-user-edit.\n",
        author="user",
        message="hand edit",
    )
    assert "unique-user-edit" in (edited.get("content") or "")

    again = await apply_distill(store, kb_id=kb_id, workspace_id="", bundle=bundle)
    assert "alpha-notes" in again["conflicts"]
    kept = await store.get_wiki_page(kb_id, "alpha-notes")
    assert "unique-user-edit" in (kept.get("content") or "")
    draft = await store.get_wiki_page(kb_id, "alpha-notes-draft")
    assert draft and draft.get("status") == "draft"

    first_rev = (kept.get("revisions") or [])[-1]["revision_id"]
    # revisions are newest-first; last item is the earliest agent version
    rolled = await store.rollback_wiki_page(kb_id, "alpha-notes", first_rev)
    assert "unique-user-edit" not in (rolled.get("content") or "")

    graph = await store.list_graph(kb_id)
    page_nodes = [n for n in graph["nodes"] if n["kind"] == "page"]
    assert len(page_nodes) >= 3
    assert any(e["rel"] == "wiki_link" for e in graph["edges"])

    hits = await store.search("wiki_beta", kb_id=kb_id, limit=8)
    wiki_hits = [h for h in hits if h.get("cite_kind") == "wiki" or str(h.get("source")) == "wiki"]
    assert wiki_hits
    assert any("wiki:" in str(h.get("citation") or "") for h in wiki_hits)

    listed = await store.list_docs(kb_id=kb_id, limit=50)
    assert all(str(d.get("source") or "") != "wiki" for d in listed)
    stats = await store.stats(kb_id=kb_id)
    assert stats.get("wiki_pages", 0) >= 3

    grounded = await retrieve_bound_knowledge("wiki_beta", {"weknora_kb_id": kb_id}, store=store)
    assert grounded["hit_count"] >= 1
    assert any(
        "wiki:" in str(h.get("citation") or "") or h.get("cite_kind") == "wiki"
        for h in grounded.get("results") or []
    )


@pytest.mark.asyncio
async def test_wiki_rpc_empty_then_distill(store: KnowledgeStore, monkeypatch):
    monkeypatch.delenv("GLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("KB_WIKI", "1")
    monkeypatch.setenv("KB_INGEST_SYNC", "1")
    await store.upsert(
        doc_id="rpc_doc",
        title="RPC Distill Doc",
        content="# RPC Distill Doc\n\nUnique rpc-wiki-marker paragraph.\n",
        source="test",
        kb_id="local:default",
    )
    app = FastAPI()
    register_knowledge_rpc(app, {"session_factory": store.session_factory})
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        empty = await client.get("/rpc/knowledge/wiki/pages", params={"kb_id": "local:default"})
        assert empty.status_code == 200
        assert empty.json()["ok"] is True
        assert empty.json()["data"]["pages"] == []
        graph = await client.get("/rpc/knowledge/graph", params={"kb_id": "local:default"})
        assert graph.status_code == 200
        assert graph.json()["data"]["nodes"] == []
        distilled = await client.post(
            "/rpc/knowledge/wiki/distill",
            json={"kb_id": "local:default"},
        )
        assert distilled.status_code == 200
        assert distilled.json()["ok"] is True
        listed = await client.get("/rpc/knowledge/wiki/pages", params={"kb_id": "local:default"})
        slugs = {p["slug"] for p in listed.json()["data"]["pages"]}
        assert "rpc-distill-doc" in slugs
        page = await client.get(
            "/rpc/knowledge/wiki/pages/rpc-distill-doc",
            params={"kb_id": "local:default"},
        )
        assert page.json()["ok"] is True
        assert "rpc-wiki-marker" in (page.json()["data"].get("content") or "")
