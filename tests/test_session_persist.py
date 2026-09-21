"""Local MemoryBroker chat history must survive process restart."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from src.common.config import Settings
from src.infrastructure.memory_broker import MemoryBroker


def _settings(tmp_path: Path) -> Settings:
    return Settings(redis_url="memory://local", session_persist_dir=str(tmp_path))


@pytest.mark.asyncio
async def test_persisted_sessions_reload_on_new_broker(tmp_path: Path):
    settings = _settings(tmp_path)
    first = MemoryBroker(settings, persist=True)
    await first.connect()
    await first.set_session(
        "s1",
        {
            "session_id": "s1",
            "title": "麦克斯韦",
            "updated_at": "2026-09-21T12:00:00+00:00",
            "messages": [{"role": "user", "content": "写一组方程"}],
            "cwd": "E:/work",
        },
    )
    await first.set_session(
        "s2",
        {
            "session_id": "s2",
            "title": "新对话",
            "updated_at": "2026-09-21T13:00:00+00:00",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )

    second = MemoryBroker(settings, persist=True)
    await second.connect()
    listed = await second.list_sessions()
    assert [row["session_id"] for row in listed] == ["s2", "s1"]
    got = await second.get_session("s1")
    assert got is not None
    assert got["title"] == "麦克斯韦"
    assert got["messages"][0]["content"] == "写一组方程"
    assert got["cwd"] == "E:/work"


@pytest.mark.asyncio
async def test_delete_session_removes_disk_file(tmp_path: Path):
    settings = _settings(tmp_path)
    broker = MemoryBroker(settings, persist=True)
    await broker.connect()
    await broker.set_session("gone", {"session_id": "gone", "messages": []})
    assert (tmp_path / "gone.json").is_file()
    await broker.delete_session("gone")
    assert not (tmp_path / "gone.json").exists()

    later = MemoryBroker(settings, persist=True)
    await later.connect()
    assert await later.get_session("gone") is None
    assert await later.list_sessions() == []


@pytest.mark.asyncio
async def test_tests_without_persist_do_not_write_disk(tmp_path: Path):
    settings = _settings(tmp_path)
    broker = MemoryBroker(settings)
    await broker.connect()
    await broker.set_session("ephemeral", {"session_id": "ephemeral", "messages": []})
    assert list(tmp_path.glob("*.json")) == []


@pytest.mark.asyncio
async def test_concurrent_append_and_patch_keep_messages(tmp_path: Path):
    settings = _settings(tmp_path)
    broker = MemoryBroker(settings, persist=True)
    await broker.set_session(
        "s1",
        {"session_id": "s1", "messages": [{"role": "user", "content": "a"}], "title": "旧"},
    )

    async def append() -> None:
        await broker.append_session_message("s1", {"role": "assistant", "content": "b"})

    async def patch() -> None:
        await broker.patch_session("s1", {"title": "新标题"})

    await asyncio.gather(append(), patch())
    sess = await broker.get_session("s1")
    assert sess is not None
    assert [m["content"] for m in sess["messages"]] == ["a", "b"]
    assert sess["title"] == "新标题"


@pytest.mark.asyncio
async def test_list_sessions_includes_fork_fields():
    broker = MemoryBroker(Settings(redis_url="memory://"))
    await broker.set_session(
        "child",
        {
            "session_id": "child",
            "title": "Fork",
            "messages": [],
            "parent_id": "parent",
            "forked_from": "parent",
            "fork_point_index": 2,
            "preset_name": "review",
        },
    )
    row = (await broker.list_sessions())[0]
    assert row["parent_id"] == "parent"
    assert row["forked_from"] == "parent"
    assert row["fork_point_index"] == 2
    assert row["preset_name"] == "review"
