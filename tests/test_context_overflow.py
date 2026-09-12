"""Wave C: context overflow detection + event ring helpers."""

import asyncio

import pytest

from src.common.config import get_settings
from src.core_kernel.context_overflow import is_context_overflow_error
from src.infrastructure.memory_broker import MemoryBroker


@pytest.mark.parametrize(
    "text,expect",
    [
        ("context_length_exceeded", True),
        ("This model's maximum context length is 128000 tokens", True),
        ("prompt is too long", True),
        ("HTTP 429 rate limit", False),
        ("", False),
    ],
)
def test_is_context_overflow_error(text, expect):
    assert is_context_overflow_error(text) is expect
    assert is_context_overflow_error(RuntimeError(text)) is expect


@pytest.mark.asyncio
async def test_event_ring_replay_after_cursor():
    broker = MemoryBroker(get_settings())
    await broker.connect()
    sid = "sess_wave_c"
    for i in range(5):
        await broker.append_session_event(
            sid,
            {"event_id": f"evt_{i}", "event_type": "task.delta", "payload": {"i": i}},
            maxlen=10,
        )
    missed = await broker.list_session_events_after(sid, "evt_2")
    assert [e["event_id"] for e in missed] == ["evt_3", "evt_4"]
    full = await broker.list_session_events_after(sid, "")
    assert len(full) == 5
    # Unknown cursor → full log (safer than empty)
    assert len(await broker.list_session_events_after(sid, "evt_missing")) == 5


@pytest.mark.asyncio
async def test_kv_roundtrip():
    broker = MemoryBroker(get_settings())
    await broker.connect()
    await broker.kv_set("subagent:sa_test", {"id": "sa_test", "status": "idle"})
    got = await broker.kv_get("subagent:sa_test")
    assert got and got["id"] == "sa_test"
    await broker.kv_delete("subagent:sa_test")
    assert await broker.kv_get("subagent:sa_test") is None
