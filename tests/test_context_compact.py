"""Tests for layered context compaction."""

from src.common.schemas import ChatMessage, ChatRole
from src.core_kernel.context_compact import (
    COMPACTION_PROFILES,
    compact_messages,
    estimate_tokens,
    resolve_compaction_params,
)


def _msg(role: str, content: str) -> ChatMessage:
    return ChatMessage(role=ChatRole(role), content=content)


def test_compaction_profiles():
    cons = resolve_compaction_params("conservative")
    bal = resolve_compaction_params("balanced")
    agg = resolve_compaction_params("aggressive")
    assert cons["collapse_trigger_ratio"] > bal["collapse_trigger_ratio"] > agg["collapse_trigger_ratio"]
    assert cons["soft_msg_chars"] > bal["soft_msg_chars"] > agg["soft_msg_chars"]
    assert set(COMPACTION_PROFILES) == {"conservative", "balanced", "aggressive"}
    # Unknown → balanced
    assert resolve_compaction_params("nope") == bal


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
        ChatMessage(
            role=ChatRole.ASSISTANT,
            content="",
            metadata={"tool_calls": [{"id": "t1", "name": "read_file"}]},
        ),
        ChatMessage(role=ChatRole.TOOL, content=huge, tool_call_id="t1", name="read_file"),
        _msg("user", "continue"),
    ]
    out = compact_messages(msgs, model_name="gpt-4o", context_window=32_000)
    tool = next(m for m in out if m.role == ChatRole.TOOL)
    assert len(tool.content or "") < 40_000
    assert "truncated" in (tool.content or "")


def test_conservative_compacts_later_than_aggressive():
    msgs = [_msg("system", "sys")]
    for i in range(20):
        msgs.append(_msg("user", f"q{i} " + ("x" * 400)))
        msgs.append(_msg("assistant", f"a{i} " + ("y" * 400)))
    window = 32_000
    cons = compact_messages(
        msgs, model_name="gpt-4o", context_window=window, aggressiveness="conservative"
    )
    agg = compact_messages(
        msgs, model_name="gpt-4o", context_window=window, aggressiveness="aggressive"
    )
    # Aggressive should drop/summarize at least as much as conservative (or equal).
    assert sum(estimate_tokens(m.content or "") for m in agg) <= sum(
        estimate_tokens(m.content or "") for m in cons
    ) + 50
