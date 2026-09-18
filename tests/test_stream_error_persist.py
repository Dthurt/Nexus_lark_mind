"""Stream failures must be written onto the session so refresh still shows them."""

from __future__ import annotations

import pytest

from src.agent_orchestrator.session_context import SessionContext
from src.agent_orchestrator.task_dispatcher import TaskDispatcher
from src.common.config import Settings
from src.common.schemas import ChannelType, ChatMessage, ChatRole, StandardTask
from src.common.session_errors import (
    build_error_message,
    format_error_display,
    is_persisted_error,
    model_history_messages,
)
from src.infrastructure.memory_broker import MemoryBroker


def test_format_error_display_matches_live_ui():
    assert format_error_display("deepseek-self stream HTTP 400: bad") == (
        "错误：deepseek-self stream HTTP 400: bad"
    )
    assert format_error_display("限流 429").startswith("⚠️")
    assert format_error_display("x", cancelled=True) == "已停止生成。"


def test_build_error_message_is_assistant_kind_error():
    msg = build_error_message("deepseek-self stream HTTP 400", task_id="t1")
    dumped = msg.model_dump(mode="json")
    assert dumped["role"] == "assistant"
    assert dumped["metadata"]["kind"] == "error"
    assert dumped["metadata"]["error"] == "deepseek-self stream HTTP 400"
    assert dumped["content"].startswith("错误：")
    assert is_persisted_error(dumped)
    assert model_history_messages([dumped, {"role": "user", "content": "hi"}]) == [
        {"role": "user", "content": "hi"}
    ]


@pytest.mark.asyncio
async def test_persist_turn_error_saves_user_and_error():
    broker = MemoryBroker(Settings(redis_url="memory://"))
    sessions = SessionContext(broker)
    await sessions.persist_turn_error(
        "s1",
        "deepseek-self stream HTTP 400: tool_calls",
        user_content="帮我看看",
        task_id="task_1",
    )
    msgs = await sessions.load_messages("s1")
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[0]["content"] == "帮我看看"
    assert msgs[1]["metadata"]["kind"] == "error"
    assert "HTTP 400" in msgs[1]["content"]

    # Idempotent for the same task_id
    await sessions.persist_turn_error(
        "s1",
        "deepseek-self stream HTTP 400: tool_calls",
        user_content="帮我看看",
        task_id="task_1",
    )
    assert len(await sessions.load_messages("s1")) == 2


class _FailingKernel:
    async def stream_post(self, *_args, **_kwargs):
        yield {"done": True, "error": "deepseek-self stream HTTP 400: bad tool_calls"}


class _DummyQueue:
    async def enqueue(self, task):
        return task


@pytest.mark.asyncio
async def test_dispatcher_stream_error_is_saved_on_session():
    broker = MemoryBroker(Settings(redis_url="memory://"))
    sessions = SessionContext(broker)
    dispatcher = TaskDispatcher(_DummyQueue(), sessions, _FailingKernel(), broker)
    task = StandardTask(
        task_id="task_err",
        session_id="s_err",
        channel=ChannelType.WEB,
        user_id="web-user",
        content="发一条测试",
        stream=True,
    )
    await dispatcher.dispatch(task)
    msgs = await sessions.load_messages("s_err")
    roles = [m.get("role") for m in msgs]
    assert "user" in roles
    errors = [m for m in msgs if is_persisted_error(m)]
    assert len(errors) == 1
    assert "HTTP 400" in errors[0]["content"]
    assert errors[0]["metadata"]["task_id"] == "task_err"
    # Model history must not treat the error as a normal assistant reply.
    assert all(not is_persisted_error(m) for m in model_history_messages(msgs))


@pytest.mark.asyncio
async def test_ensure_user_message_does_not_duplicate_same_task():
    broker = MemoryBroker(Settings(redis_url="memory://"))
    sessions = SessionContext(broker)
    await sessions.ensure("s2", user_id="web-user", channel="web")
    assert await sessions.ensure_user_message("s2", "hello", task_id="t1") is True
    assert await sessions.ensure_user_message("s2", "hello", task_id="t1") is False
    await sessions.append("s2", ChatMessage(role=ChatRole.ASSISTANT, content="ok"))
    assert await sessions.ensure_user_message("s2", "hello", task_id="t2") is True
    msgs = await sessions.load_messages("s2")
    users = [m for m in msgs if m["role"] == "user"]
    assert len(users) == 2
