"""Session append must never invent an empty history blob."""

from __future__ import annotations

import pytest

from src.common.config import Settings
from src.infrastructure.memory_broker import MemoryBroker


@pytest.mark.asyncio
async def test_memory_append_refuses_missing_session():
    broker = MemoryBroker(Settings(redis_url="memory://"))
    with pytest.raises(KeyError):
        await broker.append_session_message("missing", {"role": "user", "content": "hi"})


@pytest.mark.asyncio
async def test_memory_append_keeps_existing_history():
    broker = MemoryBroker(Settings(redis_url="memory://"))
    await broker.set_session("s1", {"session_id": "s1", "messages": [{"role": "user", "content": "a"}]})
    sess = await broker.append_session_message("s1", {"role": "assistant", "content": "b"})
    assert [m["content"] for m in sess["messages"]] == ["a", "b"]


@pytest.mark.asyncio
async def test_memory_patch_preserves_messages():
    broker = MemoryBroker(Settings(redis_url="memory://"))
    await broker.set_session(
        "s1",
        {
            "session_id": "s1",
            "messages": [{"role": "user", "content": "a"}],
            "inbox": [{"id": "i1", "kind": "steer", "content": "go"}],
        },
    )
    # Concurrent append after a stale snapshot
    await broker.append_session_message("s1", {"role": "assistant", "content": "b"})
    await broker.patch_session("s1", {"inbox": [], "messages": [{"role": "user", "content": "STALE"}]})
    sess = await broker.get_session("s1")
    assert sess["inbox"] == []
    assert [m["content"] for m in sess["messages"]] == ["a", "b"]


@pytest.mark.asyncio
async def test_memory_update_session_reruns_mutator_logic():
    broker = MemoryBroker(Settings(redis_url="memory://"))
    await broker.set_session(
        "s1",
        {
            "session_id": "s1",
            "messages": [{"role": "user", "content": "a"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 0, "total_tokens": 1, "cached_tokens": 0},
        },
    )
    await broker.append_session_message("s1", {"role": "tool", "content": "ok"})

    def mutate(session: dict) -> None:
        cur = session.get("usage") or {}
        session["usage"] = {
            "prompt_tokens": int(cur.get("prompt_tokens") or 0) + 2,
            "completion_tokens": int(cur.get("completion_tokens") or 0) + 3,
            "total_tokens": int(cur.get("prompt_tokens") or 0) + 2 + int(cur.get("completion_tokens") or 0) + 3,
            "cached_tokens": 0,
        }
        # Attempt to clobber messages — must be ignored.
        session["messages"] = [{"role": "user", "content": "STALE"}]

    await broker.update_session("s1", mutate, preserve_messages=True)
    sess = await broker.get_session("s1")
    assert [m["content"] for m in sess["messages"]] == ["a", "ok"]
    assert sess["usage"]["prompt_tokens"] == 3
    assert sess["usage"]["completion_tokens"] == 3
