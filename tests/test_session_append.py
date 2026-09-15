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
