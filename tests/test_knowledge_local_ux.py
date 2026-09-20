"""Local multi-KB, ingest jobs, URL/HTML, chunk edit — WeKnora-like UX without WeKnora."""

from __future__ import annotations

import base64

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.core_kernel.kb_grounding import retrieve_bound_knowledge
from src.core_kernel.knowledge_rpc import register_knowledge_rpc
from src.core_kernel.plugin_runtime import knowledge_embeddings as ke
from src.core_kernel.plugin_runtime.knowledge_ingest import html_to_text, read_bytes_as_text
from src.core_kernel.plugin_runtime.knowledge_jobs import enqueue_file_job, process_ingest_job
from src.core_kernel.plugin_runtime.knowledge_scope import (
    ALL_LOCAL_KB_ID,
    DEFAULT_LOCAL_KB_ID,
    is_local_kb_id,
    is_remote_kb_id,
    normalize_local_kb_id,
)
from src.core_kernel.plugin_runtime.knowledge_store import KnowledgeStore, content_hash
from src.core_kernel.plugin_runtime.knowledge_url import validate_ingest_url
from src.infrastructure.storage.database import Base as AppBase


@pytest.fixture
async def store(tmp_path):
    url = f"sqlite+aiosqlite:///{(tmp_path / 'kb.db').as_posix()}"
    engine = create_async_engine(url, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(AppBase.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    kb = KnowledgeStore(factory)
    await kb.ensure_schema()
    yield kb
    await engine.dispose()


def test_local_kb_id_helpers():
    assert is_local_kb_id("") is True
    assert is_local_kb_id("local:default") is True
    assert is_local_kb_id("kb-remote") is False
    assert is_remote_kb_id("kb-remote") is True
    assert normalize_local_kb_id("") == DEFAULT_LOCAL_KB_ID
    assert normalize_local_kb_id("local:legal") == "local:legal"


def test_html_to_text_strips_scripts():
    html = "<html><script>alert(1)</script><h1>Hello</h1><p>Body</p></html>"
    text = html_to_text(html)
    assert "Hello" in text
    assert "Body" in text
    assert "alert" not in text


def test_read_html_bytes():
    raw = b"<html><body><h1>Spec</h1><p>NLM local library</p></body></html>"
    text, note = read_bytes_as_text(raw, ".html", filename="page.html")
    assert "NLM local library" in text
    assert "html" in note


def test_url_ssrf_blocked():
    with pytest.raises(ValueError):
        validate_ingest_url("http://127.0.0.1/secret")
    with pytest.raises(ValueError):
        validate_ingest_url("file:///etc/passwd")
    with pytest.raises(ValueError):
        validate_ingest_url("http://localhost/x")


def test_glm_key_enables_hybrid_by_default(monkeypatch):
    monkeypatch.delenv("KB_EMBEDDING_BASE_URL", raising=False)
    monkeypatch.delenv("WEMM_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("KB_EMBEDDING_ENABLED", raising=False)
    monkeypatch.setenv("GLM_API_KEY", "glm-test-key")
    monkeypatch.delenv("GLM_BASE_URL", raising=False)
    assert ke.embeddings_configured() is True
    assert ke.embedding_backend() == "glm"
    assert ke.embedding_model() == "embedding-3"
    assert ke.embedding_base_url().endswith("/api/paas/v4")
    monkeypatch.setenv("KB_EMBEDDING_ENABLED", "0")
    assert ke.embeddings_configured() is False


@pytest.mark.asyncio
async def test_multi_kb_search_isolation(store):
    other = await store.create_local_kb(name="Legal", workspace_id="ws1")
    await store.upsert(
        doc_id="d-default",
        title="Default",
        content="alpha marker in default library",
        workspace_id="ws1",
        kb_id=DEFAULT_LOCAL_KB_ID,
        content_hash_value=content_hash("alpha marker in default library"),
    )
    await store.upsert(
        doc_id="d-legal",
        title="Legal",
        content="beta marker in legal library",
        workspace_id="ws1",
        kb_id=other["kb_id"],
        content_hash_value=content_hash("beta marker in legal library"),
    )
    default_hits = await store.search("marker", workspace_id="ws1", kb_id=DEFAULT_LOCAL_KB_ID)
    legal_hits = await store.search("marker", workspace_id="ws1", kb_id=other["kb_id"])
    default_ids = {h["doc_id"] for h in default_hits}
    legal_ids = {h["doc_id"] for h in legal_hits}
    assert "d-default" in default_ids
    assert "d-legal" not in default_ids
    assert "d-legal" in legal_ids
    assert "d-default" not in legal_ids


@pytest.mark.asyncio
async def test_search_all_local_kbs_unions_libraries(store):
    other = await store.create_local_kb(name="Legal", workspace_id="ws1")
    await store.upsert(
        doc_id="d-default-all",
        title="Default",
        content="shared marker in default library",
        workspace_id="ws1",
        kb_id=DEFAULT_LOCAL_KB_ID,
        content_hash_value=content_hash("shared marker in default library"),
    )
    await store.upsert(
        doc_id="d-legal-all",
        title="Legal",
        content="shared marker in legal library",
        workspace_id="ws1",
        kb_id=other["kb_id"],
        content_hash_value=content_hash("shared marker in legal library"),
    )
    hits = await store.search("shared marker", workspace_id="ws1", kb_id=ALL_LOCAL_KB_ID)
    ids = {h["doc_id"] for h in hits}
    assert "d-default-all" in ids
    assert "d-legal-all" in ids
    default_hit = next(h for h in hits if h["doc_id"] == "d-default-all")
    assert default_hit.get("snapshot")
    assert default_hit.get("match_kind") in {"keyword", "semantic"}
    assert "#c" in str(default_hit.get("cite_href") or "")


@pytest.mark.asyncio
async def test_ingest_job_file_progress(store, tmp_path, monkeypatch):
    monkeypatch.setenv("KB_INGEST_SYNC", "1")
    monkeypatch.chdir(tmp_path)
    job = await enqueue_file_job(
        store,
        filename="note.md",
        raw=b"# Hello job\n\nqueued document body",
        kb_id=DEFAULT_LOCAL_KB_ID,
        workspace_id="ws-job",
    )
    assert job["status"] == "completed"
    assert job["progress"] == 100
    stored = await store.get(job["doc_id"])
    assert stored and "queued document body" in stored["content"]
    assert stored["kb_id"] == DEFAULT_LOCAL_KB_ID


@pytest.mark.asyncio
async def test_chunk_edit(store):
    await store.upsert(
        doc_id="c1",
        title="Chunks",
        content="First paragraph about apples.\n\nSecond paragraph about oranges.",
        workspace_id="ws1",
        content_hash_value=content_hash("First paragraph about apples.\n\nSecond paragraph about oranges."),
    )
    doc = await store.get("c1", include_chunks=True)
    assert doc and doc.get("chunks")
    cid = doc["chunks"][0]["chunk_id"]
    updated = await store.update_chunk(cid, content="First paragraph about pears.")
    assert updated and "pears" in updated["content"]
    again = await store.get("c1", include_chunks=True)
    assert any("pears" in (c.get("content") or "") for c in again["chunks"])


@pytest.mark.asyncio
async def test_retrieve_local_prefixed_kb_skips_weknora(store):
    other = await store.create_local_kb(name="Specs", workspace_id="ws1")
    await store.upsert(
        doc_id="spec1",
        title="Spec",
        content="NLM uses a local SQLite knowledge base for the workbench.",
        workspace_id="ws1",
        kb_id=other["kb_id"],
        content_hash_value=content_hash("NLM uses a local SQLite knowledge base for the workbench."),
    )

    async def boom(*_a, **_k):
        raise AssertionError("local: ids must not call weknora")

    out = await retrieve_bound_knowledge(
        "SQLite knowledge",
        {"weknora_kb_id": other["kb_id"], "workspace_id": "ws1"},
        store=store,
        weknora_search_fn=boom,
    )
    assert out["source"] == "local"
    assert out["kb_id"] == other["kb_id"]
    assert out["hit_count"] >= 1


@pytest.mark.asyncio
async def test_rpc_local_kb_and_ingest(store, tmp_path, monkeypatch):
    monkeypatch.setenv("KB_INGEST_SYNC", "1")
    monkeypatch.chdir(tmp_path)
    app = FastAPI()
    register_knowledge_rpc(app, {"session_factory": store.session_factory})
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post("/rpc/knowledge/kbs", json={"name": "产品手册", "workspace_id": "ws"})
        assert created.status_code == 200
        kb = created.json()["data"]
        assert kb["id"].startswith("local:")
        listed = await client.get("/rpc/knowledge/kbs", params={"workspace_id": "ws"})
        ids = {row["id"] for row in listed.json()["data"]["knowledge_bases"]}
        assert DEFAULT_LOCAL_KB_ID in ids
        assert kb["id"] in ids
        raw = b"<html><body><p>URL-like html ingest</p></body></html>"
        ingest = await client.post(
            "/rpc/knowledge/ingest",
            json={
                "filename": "page.html",
                "content_b64": base64.b64encode(raw).decode("ascii"),
                "workspace_id": "ws",
                "kb_id": kb["id"],
            },
        )
        assert ingest.status_code == 200
        body = ingest.json()
        assert body["ok"] is True
        job = body["data"]["jobs"][0]
        assert job["status"] == "completed"
        chunks = await client.get(
            f"/rpc/knowledge/docs/{job['doc_id']}", params={"include_chunks": True}
        )
        doc = chunks.json()["data"]
        cid = doc["chunks"][0]["chunk_id"]
        from urllib.parse import quote

        patched = await client.patch(
            f"/rpc/knowledge/chunks/{quote(cid, safe='')}", json={"content": "edited chunk body"}
        )
        assert patched.json()["ok"] is True
        assert "edited chunk body" in patched.json()["data"]["content"]
        strat = await client.patch(
            f"/rpc/knowledge/kbs/{kb['id']}", json={"chunk_strategy": "heading"}
        )
        assert strat.json()["ok"] is True
        assert strat.json()["data"]["chunk_strategy"] == "heading"


@pytest.mark.asyncio
async def test_sync_workspace_docs_uses_bound_kb(store, tmp_path):
    from src.core_kernel.plugin_runtime.knowledge_sync import sync_workspace_docs

    other = await store.create_local_kb(name="SyncLib", workspace_id="ws-sync")
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "guide.md").write_text("# Guide\n\nsync-kb-marker-unique\n", encoding="utf-8")
    result = await sync_workspace_docs(
        store, str(tmp_path), workspace_id="ws-sync", kb_id=other["kb_id"]
    )
    assert result["ok"] is True
    assert result["kb_id"] == other["kb_id"]
    assert result["added"] >= 1
    listed = await store.list_docs(workspace_id="ws-sync", kb_id=other["kb_id"])
    default_docs = await store.list_docs(workspace_id="ws-sync", kb_id=DEFAULT_LOCAL_KB_ID)
    other_ids = {row["doc_id"] for row in listed}
    default_ids = {row["doc_id"] for row in default_docs}
    assert other_ids
    assert not other_ids.intersection(default_ids)
    remote = await sync_workspace_docs(
        store, str(tmp_path), workspace_id="ws-sync", kb_id="wk-remote-1"
    )
    assert remote.get("noop") is True


@pytest.mark.asyncio
async def test_chunker_preview_relative_path_and_retry(store, tmp_path, monkeypatch):
    monkeypatch.setenv("KB_INGEST_SYNC", "1")
    monkeypatch.chdir(tmp_path)
    app = FastAPI()
    register_knowledge_rpc(app, {"session_factory": store.session_factory})
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        preview = await client.post(
            "/rpc/knowledge/chunker/preview",
            json={
                "text": "# One\n\n" + ("alpha " * 80) + "\n\n# Two\n\n" + ("beta " * 80),
                "strategy": "heading",
            },
        )
        assert preview.status_code == 200
        pdata = preview.json()
        assert pdata["ok"] is True
        assert pdata["data"]["count"] >= 1
        assert pdata["data"]["chunks"]
        assert pdata["data"]["strategy"] == "heading"

        rel = await client.post(
            "/rpc/knowledge/ingest",
            json={
                "filename": "docs/api/note.md",
                "content_b64": base64.b64encode(b"# Rel\n\nrelative path body").decode("ascii"),
                "workspace_id": "ws-rel",
                "kb_id": DEFAULT_LOCAL_KB_ID,
            },
        )
        assert rel.json()["ok"] is True
        job = rel.json()["data"]["jobs"][0]
        assert job["status"] == "completed"
        stored = await store.get(job["doc_id"])
        assert stored["source_uri"] == "docs/api/note.md"
        assert "dir:docs/api" in (stored.get("tags") or "")

        await store.create_ingest_job(
            job_id="job_retry_me",
            kind="file",
            filename="retry.md",
            source_uri="retry.md",
            kb_id=DEFAULT_LOCAL_KB_ID,
            workspace_id="ws-rel",
            status="failed",
            progress=100,
            message="failed",
        )
        await store.update_ingest_job("job_retry_me", error="boom")
        from src.core_kernel.plugin_runtime.knowledge_jobs import INGEST_ROOT

        INGEST_ROOT.mkdir(parents=True, exist_ok=True)
        (INGEST_ROOT / "job_retry_me").write_bytes(b"# Retry\n\nretry body here")
        again = await client.post("/rpc/knowledge/ingest/jobs/job_retry_me/retry")
        assert again.json()["ok"] is True
        row = again.json()["data"]
        assert row["status"] == "completed"
        doc = await store.get(row["doc_id"])
        assert doc and "retry body" in doc["content"]
        meta = await client.patch(
            f"/rpc/knowledge/docs/{row['doc_id']}",
            json={"title": "Retried note", "tags": "retry,manual"},
        )
        assert meta.json()["ok"] is True
        assert meta.json()["data"]["title"] == "Retried note"
        assert "retry" in meta.json()["data"]["tags"]
