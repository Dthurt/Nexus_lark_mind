"""Recorded WeKnora HTTP shapes — search / list KBs / push / health. No live server."""

from __future__ import annotations

import pytest

from tests.weknora_http_harness import install_weknora_http_fixtures


API_KEY = "fixture-api-key"


@pytest.fixture
def weknora_env(monkeypatch):
    monkeypatch.setenv("WEKNORA_BASE_URL", "http://weknora.test")
    monkeypatch.setenv("WEKNORA_API_KEY", API_KEY)
    monkeypatch.setenv("WEKNORA_KB_ID", "kb-1")
    rec = install_weknora_http_fixtures(monkeypatch)
    return rec


@pytest.mark.asyncio
async def test_recorded_health_list_kbs_search_push(weknora_env):
    from src.core_kernel.plugin_runtime import weknora_client as wc

    rec = weknora_env

    health = await wc.weknora_health()
    assert health.get("ok") is True
    assert health.get("online") is True
    hreq = rec.find("GET", "/api/v1/knowledge-bases")
    rec.assert_auth(hreq, API_KEY)
    assert hreq["path"] == "/api/v1/knowledge-bases"

    kbs = await wc.weknora_list_knowledge_bases()
    assert kbs.get("ok") is True
    assert kbs["knowledge_bases"][0]["id"] == "kb-1"
    kb_req = rec.find("GET", "/api/v1/knowledge-bases")
    rec.assert_auth(kb_req, API_KEY)

    search = await wc.weknora_search("canned query", kb_id="kb-1", limit=5)
    assert search.get("ok") is True
    assert search.get("endpoint") == "/api/v1/knowledge-search"
    assert search["results"][0]["title"] == "Canned Doc"
    sreq = rec.find("POST", "/api/v1/knowledge-search")
    rec.assert_auth(sreq, API_KEY)
    assert sreq["body"]["query"] == "canned query"
    assert sreq["body"]["knowledge_base_id"] == "kb-1"

    push = await wc.weknora_push_document(
        title="Note",
        content="hello weknora sync",
        kb_id="kb-1",
        metadata={"nlm_doc_id": "local1", "content_hash": "abc"},
    )
    assert push.get("ok") is True
    assert push.get("knowledge_id") == "remote-canned"
    preq = rec.find("POST", "/knowledge/manual")
    rec.assert_auth(preq, API_KEY)
    assert preq["path"] == "/api/v1/knowledge-bases/kb-1/knowledge/manual"
    assert preq["body"]["title"] == "Note"
    assert preq["body"]["content"] == "hello weknora sync"
    assert preq["body"]["metadata"]["nlm_doc_id"] == "local1"


@pytest.mark.asyncio
async def test_recorded_list_knowledge_shape(weknora_env):
    from src.core_kernel.plugin_runtime import weknora_client as wc

    rec = weknora_env
    listed = await wc.weknora_list_knowledge("kb-1", page=1, page_size=20)
    assert listed.get("ok") is True
    assert listed["items"][0]["nlm_doc_id"] == "local1"
    lreq = rec.find("GET", "/api/v1/knowledge-bases/kb-1/knowledge")
    rec.assert_auth(lreq, API_KEY)
    assert lreq["path"] == "/api/v1/knowledge-bases/kb-1/knowledge"


@pytest.mark.asyncio
async def test_recorded_get_and_update_knowledge(weknora_env):
    from src.core_kernel.plugin_runtime import weknora_client as wc

    rec = weknora_env
    got = await wc.weknora_get_knowledge("remote-canned")
    assert got.get("ok") is True
    assert got.get("content") == "full canned remote body"
    greq = rec.find("GET", "/api/v1/knowledge/remote-canned")
    rec.assert_auth(greq, API_KEY)

    updated = await wc.weknora_update_document(
        knowledge_id="remote-canned",
        title="Note",
        content="updated body",
        kb_id="kb-1",
        metadata={"nlm_doc_id": "local1"},
    )
    assert updated.get("ok") is True
    assert updated.get("updated") is True
    ureq = rec.find("PUT", "/api/v1/knowledge/remote-canned")
    rec.assert_auth(ureq, API_KEY)
    assert ureq["body"]["content"] == "updated body"


@pytest.mark.asyncio
async def test_recorded_push_omits_knowledge_id_titlehash(weknora_env, tmp_path):
    """Fixture: manual POST with empty knowledge_id still records title/hash identity."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from src.core_kernel.plugin_runtime.knowledge_store import Base, KnowledgeStore, content_hash
    from src.core_kernel.plugin_runtime.knowledge_sync import (
        record_weknora_push_identity,
        resolve_local_doc_id_for_remote,
        weknora_titlehash_key,
    )
    from src.core_kernel.plugin_runtime import weknora_client as wc

    rec = weknora_env
    rec.canned["knowledge_manual"] = rec.canned["knowledge_manual_no_id"]
    rec.canned["knowledge_list"] = rec.canned["knowledge_list_no_id"]

    push = await wc.weknora_push_document(title="Note", content="hello weknora sync", kb_id="kb-1")
    assert push.get("ok") is True
    assert not push.get("knowledge_id")

    url = f"sqlite+aiosqlite:///{(tmp_path / 'kb.db').as_posix()}"
    engine = create_async_engine(url, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    store = KnowledgeStore(async_sessionmaker(engine, expire_on_commit=False))
    await store.ensure_schema()
    body = "hello weknora sync"
    digest = content_hash(body)
    await store.upsert(
        doc_id="local1",
        title="Note",
        content="dirty after omitted id",
        workspace_id="ws1",
        content_hash_value=content_hash("dirty after omitted id"),
    )
    await record_weknora_push_identity(
        store,
        kb_id="kb-1",
        local_doc_id="local1",
        remote_id="",
        digest=digest,
        workspace_id="ws1",
        title="Note",
    )
    doc_id, reason = await resolve_local_doc_id_for_remote(
        store,
        kb_id="kb-1",
        remote_id="",
        workspace_id="ws1",
        digest=digest,
        title="Note",
    )
    assert doc_id == "local1"
    assert reason == "titlehash"
    assert weknora_titlehash_key("Note", digest).startswith("titlehash:")
    await engine.dispose()
