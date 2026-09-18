"""Bound-KB retrieval: session id (not first listed), local vs WeKnora, inject."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.common.schemas import ChatMessage, ChatRole
from src.core_kernel.kb_grounding import (
    apply_turn_grounding,
    bound_weknora_kb_id,
    format_grounding_block,
    inject_grounding,
    last_user_query,
    retrieve_bound_knowledge,
)
from src.core_kernel.plugin_runtime.knowledge_store import Base, KnowledgeStore, content_hash
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


def test_bound_kb_empty_is_local():
    assert bound_weknora_kb_id({}) == ""
    assert bound_weknora_kb_id({"weknora_kb_id": "  "}) == ""
    assert bound_weknora_kb_id({"weknora_kb_id": "kb-sess"}) == "kb-sess"


def test_last_user_query_strips_prior_grounding():
    messages = [
        ChatMessage(role=ChatRole.SYSTEM, content="sys"),
        ChatMessage(
            role=ChatRole.USER,
            content="old\n\n<knowledge_context source=\"local\" kb_id=\"local\">x</knowledge_context>",
        ),
        ChatMessage(role=ChatRole.ASSISTANT, content="ok"),
        ChatMessage(role=ChatRole.USER, content="what is the architecture?"),
    ]
    assert last_user_query(messages) == "what is the architecture?"


@pytest.mark.asyncio
async def test_retrieve_weknora_uses_session_kb_not_first(monkeypatch):
    seen = {}

    async def fake_search(q, **kwargs):
        seen["query"] = q
        seen.update(kwargs)
        return {
            "ok": True,
            "results": [
                {
                    "title": "Spec",
                    "snippet": "auth uses JWT",
                    "doc_id": "doc-9",
                    "kb_id": kwargs.get("kb_id"),
                    "citation": "Spec — remote",
                }
            ],
            "citations_md": "1. Spec",
        }

    monkeypatch.setenv("WEKNORA_BASE_URL", "http://weknora.test")
    monkeypatch.setenv("WEKNORA_KB_ID", "kb-default-should-not-win")

    out = await retrieve_bound_knowledge(
        "auth",
        {"weknora_kb_id": "kb-sess-42", "workspace_id": "ws-1"},
        weknora_search_fn=fake_search,
    )
    assert out["source"] == "weknora"
    assert out["kb_id"] == "kb-sess-42"
    assert seen["kb_id"] == "kb-sess-42"
    assert seen["session_kb_id"] == "kb-sess-42"
    assert seen["query"] == "auth"
    assert out["hit_count"] == 1
    assert out["results"][0]["kb_id"] == "kb-sess-42"


@pytest.mark.asyncio
async def test_retrieve_local_path(store):
    await store.upsert(
        doc_id="local1",
        title="Architecture",
        content="NLM uses a local SQLite knowledge base for the workbench.",
        tags="docs",
        source="manual",
        workspace_id="ws1",
        content_hash_value=content_hash("NLM uses a local SQLite knowledge base for the workbench."),
    )
    called = {"weknora": 0}

    async def boom(*_a, **_k):
        called["weknora"] += 1
        raise AssertionError("local path must not call weknora_search")

    out = await retrieve_bound_knowledge(
        "SQLite knowledge",
        {"weknora_kb_id": "", "workspace_id": "ws1"},
        store=store,
        weknora_search_fn=boom,
    )
    assert called["weknora"] == 0
    assert out["source"] == "local"
    assert out["kb_id"] == ""
    assert out["hit_count"] >= 1
    assert any("SQLite" in str(h.get("snippet") or h.get("content") or "") for h in out["results"])


@pytest.mark.asyncio
async def test_apply_turn_grounding_injects_context(store):
    await store.upsert(
        doc_id="d1",
        title="Plan",
        content="The delivery plan lives in the knowledge base.",
        tags="t",
        source="manual",
        workspace_id="",
        content_hash_value=content_hash("The delivery plan lives in the knowledge base."),
    )
    messages = [
        ChatMessage(role=ChatRole.SYSTEM, content="You are NLM."),
        ChatMessage(role=ChatRole.USER, content="Where is the delivery plan?"),
    ]
    next_msgs, event = await apply_turn_grounding(
        messages,
        {"weknora_kb_id": "", "workspace_id": ""},
        store=store,
        weknora_search_fn=AsyncMock(side_effect=AssertionError("no weknora")),
    )
    assert event is not None
    assert event["notice_kind"] == "kb_grounding"
    assert event["kb_grounding"]["source"] == "local"
    user = next_msgs[-1]
    assert "<knowledge_context" in user.content
    assert "delivery plan" in user.content.lower() or "Plan" in user.content
    assert user.metadata.get("kb_grounded") is True


@pytest.mark.asyncio
async def test_apply_turn_grounding_weknora_block_contains_bound_id():
    async def fake_search(q, **kwargs):
        return {
            "ok": True,
            "results": [{"title": "Hit", "snippet": "alpha", "doc_id": "r1", "kb_id": kwargs["kb_id"]}],
            "citations_md": "1. Hit",
        }

    messages = [ChatMessage(role=ChatRole.USER, content="explain alpha policy")]
    next_msgs, event = await apply_turn_grounding(
        messages,
        {"weknora_kb_id": "kb-only-this"},
        weknora_search_fn=fake_search,
    )
    assert event["kb_grounding"]["kb_id"] == "kb-only-this"
    assert event["kb_grounding"]["source"] == "weknora"
    block = next_msgs[-1].content
    assert 'kb_id="kb-only-this"' in block
    assert "weknora_read" in block


def test_inject_skips_when_already_grounded():
    original = ChatMessage(
        role=ChatRole.USER,
        content="q\n\n<knowledge_context source=\"local\" kb_id=\"local\">x</knowledge_context>",
    )
    out = inject_grounding([original], "<knowledge_context>y</knowledge_context>")
    assert out[0].content == original.content


def test_format_grounding_mentions_tools():
    text = format_grounding_block(
        {
            "source": "weknora",
            "kb_id": "kb-1",
            "results": [{"title": "A", "snippet": "hello", "doc_id": "d"}],
            "citations_md": "1. A",
        }
    )
    assert "weknora_read" in text
    assert "kb-1" in text
