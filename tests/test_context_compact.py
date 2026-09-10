"""Tests for layered context compaction."""

from src.common.schemas import ChatMessage, ChatRole
from src.core_kernel.context_compact import compact_messages, estimate_tokens


def _msg(role: str, content: str) -> ChatMessage:
    return ChatMessage(role=ChatRole(role), content=content)


def test_compact_keeps_system_and_recent_user():
    msgs = [_msg("system", "You are helpful.")]
    for i in range(40):
        msgs.append(_msg("user", f"question {i} " + ("x" * 800)))
        msgs.append(_msg("assistant", f"answer {i} " + ("y" * 800)))
    msgs.append(_msg("user", "FINAL_QUESTION_PLEASE_KEEP"))

    out = compact_messages(msgs, model_name="deepseek-chat", context_window=8_000)
    assert out[0].role == ChatRole.SYSTEM
    assert any("FINAL_QUESTION_PLEASE_KEEP" in (m.content or "") for m in out)
    # Must be materially smaller than the raw history
    assert sum(estimate_tokens(m.content or "") for m in out) < sum(
        estimate_tokens(m.content or "") for m in msgs
    )


def test_soft_trim_huge_tool_payload():
    huge = "Z" * 80_000
    msgs = [
        _msg("system", "sys"),
        _msg("user", "hi"),
        ChatMessage(role=ChatRole.TOOL, content=huge, tool_call_id="t1", name="read_file"),
        _msg("user", "continue"),
    ]
    out = compact_messages(msgs, model_name="gpt-4o", context_window=32_000)
    tool = next(m for m in out if m.role == ChatRole.TOOL)
    assert len(tool.content or "") < 40_000
    assert "truncated" in (tool.content or "")
