"""End-to-end-ish checks for issues #14/#15/#16 root causes."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest

from src.common.config import Settings
from src.common.rpc_client import RpcClient
from src.common.schemas import ChatMessage, ChatRole
from src.common.session_inbox import claim_kind
from src.infrastructure.memory_broker import MemoryBroker
from src.agent_orchestrator.session_context import SessionContext
import src.adapters.workspaces.ssh_store as ssh_store


@pytest.mark.asyncio
async def test_issue16_reasoning_roundtrip_and_message_order():
    """Persist reasoning on assistant metadata; concurrent inbox/usage must not scramble tools."""
    broker = MemoryBroker(Settings(redis_url="memory://"))
    sessions = SessionContext(broker)
    await broker.set_session(
        "s1",
        {
            "session_id": "s1",
            "messages": [],
            "inbox": [],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cached_tokens": 0},
            "title": "新对话",
        },
    )

    await sessions.append("s1", ChatMessage(role=ChatRole.USER, content="hello"))
    await sessions.append(
        "s1",
        ChatMessage(
            role=ChatRole.ASSISTANT,
            content="",
            metadata={"kind": "tool_call", "tool_calls": [{"id": "c1", "name": "list_dir"}]},
        ),
    )

    # Mid-stream concurrent mutations that used to clobber messages via set_session.
    await sessions.push_inbox_item("s1", kind="steer", content="nudge", source="user")
    await sessions.touch_title("s1", "hello")
    await sessions.append(
        "s1",
        ChatMessage(
            role=ChatRole.TOOL,
            content="ok",
            tool_call_id="c1",
            name="list_dir",
            metadata={"kind": "tool_result", "tool_result": {"id": "c1", "success": True}},
        ),
    )
    await sessions.add_usage("s1", {"prompt_tokens": 10, "completion_tokens": 2})

    # Kernel-style mid-turn steer claim must not wipe tools.
    holder: dict = {"claimed": []}

    def mutate(sess: dict) -> None:
        holder["claimed"] = claim_kind(sess, "steer")

    await broker.update_session("s1", mutate, preserve_messages=True)
    assert len(holder["claimed"]) == 1

    await sessions.append(
        "s1",
        ChatMessage(
            role=ChatRole.ASSISTANT,
            content="final answer",
            metadata={
                "usage": {"prompt_tokens": 10, "completion_tokens": 2},
                "model_name": "deepseek-r1",
                "model_provider": "deepseek",
                "reasoning": "step1\nstep2",
            },
        ),
    )

    msgs = await sessions.load_messages("s1")
    roles = [m.get("role") for m in msgs]
    kinds = [(m.get("metadata") or {}).get("kind") for m in msgs]
    assert roles == ["user", "assistant", "tool", "assistant"]
    assert kinds == [None, "tool_call", "tool_result", None]

    last = msgs[-1]
    meta = last.get("metadata") or {}
    assert meta.get("reasoning") == "step1\nstep2"
    # Frontend loadFromHistory reads meta.reasoning the same way.
    assert Stringish(meta.get("reasoning")) == "step1\nstep2"


def Stringish(v) -> str:
    return str(v or "")


def test_issue15_rpc_client_uses_dedicated_stream_timeout():
    client = RpcClient("http://127.0.0.1:9", timeout=120.0, stream_timeout=600.0)
    assert client.timeout == 120.0
    assert client.stream_timeout == 600.0
    assert Settings().rpc_stream_timeout_seconds == 600.0


def test_issue14_ssh_store_reload_on_file_change(tmp_path: Path, monkeypatch):
    path = tmp_path / "ssh_hosts.json"
    path.write_text(json.dumps({"hosts": []}), encoding="utf-8")
    monkeypatch.setattr(ssh_store, "STORE_PATH", path)
    ssh_store._store = None
    ssh_store._store_mtime = 0.0

    assert ssh_store.get_ssh_host_store().get("ssh_new") is None

    host = {
        "id": "ssh_new",
        "label": "dev",
        "host": "10.0.0.1",
        "port": 22,
        "username": "root",
        "auth_type": "password",
        "source": "direct",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }
    path.write_text(json.dumps({"hosts": [host]}), encoding="utf-8")
    st = path.stat()
    os.utime(path, (st.st_atime, st.st_mtime + 3))

    rec = ssh_store.get_ssh_host_store().get("ssh_new")
    assert rec is not None
    assert rec.host == "10.0.0.1"


@pytest.mark.asyncio
async def test_issue16_parallel_appends_survive_usage_patch():
    broker = MemoryBroker(Settings(redis_url="memory://"))
    sessions = SessionContext(broker)
    await broker.set_session(
        "s2",
        {
            "session_id": "s2",
            "messages": [{"role": "user", "content": "u"}],
            "inbox": [],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cached_tokens": 0},
        },
    )

    async def append_tools():
        for i in range(5):
            await sessions.append(
                "s2",
                ChatMessage(
                    role=ChatRole.ASSISTANT,
                    content="",
                    metadata={"kind": "tool_call", "tool_calls": [{"id": f"t{i}"}]},
                ),
            )
            await sessions.append(
                "s2",
                ChatMessage(
                    role=ChatRole.TOOL,
                    content=f"r{i}",
                    tool_call_id=f"t{i}",
                    metadata={"kind": "tool_result"},
                ),
            )
            await asyncio.sleep(0)

    async def poke_meta():
        for _ in range(10):
            await sessions.add_usage("s2", {"prompt_tokens": 1, "completion_tokens": 0})
            await sessions.push_inbox_item("s2", kind="queue", content="q", source="user")
            await asyncio.sleep(0)

    await asyncio.gather(append_tools(), poke_meta())
    msgs = await sessions.load_messages("s2")
    # 1 user + 5 tool_call + 5 tool_result
    assert len(msgs) == 11
    assert msgs[0]["content"] == "u"
    assert sum(1 for m in msgs if (m.get("metadata") or {}).get("kind") == "tool_call") == 5
    assert sum(1 for m in msgs if (m.get("metadata") or {}).get("kind") == "tool_result") == 5
