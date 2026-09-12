"""Subagent registry persist / hydrate via shared memory broker."""

import pytest

from src.common.schemas import ChatMessage, ChatRole
from src.core_kernel.subagent.registry import SubagentRegistry


@pytest.mark.asyncio
async def test_persist_and_hydrate_across_registries():
    reg_a = SubagentRegistry()
    rec = reg_a.create(
        label="research",
        mode="spawn",
        parent_session_id="sess_1",
        parent_task_id="task_1",
        parent_call_id="call_1",
        depth=1,
        provider="openai",
        model="gpt-test",
        workspace_cwd="/tmp",
        workspace_meta={},
        seed_messages=[ChatMessage(role=ChatRole.USER, content="hello")],
    )
    rec.status = "idle"
    rec.final_output = "done"
    await reg_a.persist(rec)

    reg_b = SubagentRegistry()
    assert reg_b.get(rec.id) is None
    loaded = await reg_b.hydrate(rec.id)
    assert loaded is not None
    assert loaded.id == rec.id
    assert loaded.status == "idle"
    assert loaded.final_output == "done"
    assert loaded.messages and loaded.messages[0].content == "hello"

    listed = await reg_b.list_for_session_async("sess_1")
    assert any(a.id == rec.id for a in listed)
