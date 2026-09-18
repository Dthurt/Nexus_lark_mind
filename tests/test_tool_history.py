"""Sanitizer must prevent DeepSeek/OpenAI HTTP 400 on broken tool_calls history."""

from src.common.schemas import ChatMessage, ChatRole
from src.core_kernel.model_gateway.openai_compat import _messages_to_openai
from src.core_kernel.tool_history import (
    MISSING_TOOL_RESULT,
    openai_tool_sequence_is_legal,
    sanitize_tool_call_messages,
)


def _asst_tools(*calls: dict, content: str = "") -> ChatMessage:
    return ChatMessage(
        role=ChatRole.ASSISTANT,
        content=content,
        metadata={"kind": "tool_call", "tool_calls": list(calls)},
    )


def _tool(call_id: str, name: str = "list_dir", content: str = "ok") -> ChatMessage:
    return ChatMessage(
        role=ChatRole.TOOL,
        content=content,
        name=name,
        tool_call_id=call_id,
        metadata={"kind": "tool_result"},
    )


def test_missing_tool_message_is_synthesized():
    """The exact 400 shape: assistant tool_calls then a user turn, no tool row."""
    history = [
        ChatMessage(role=ChatRole.SYSTEM, content="sys"),
        ChatMessage(role=ChatRole.USER, content="list files"),
        _asst_tools({"id": "c1", "name": "list_dir", "type": "function"}),
        ChatMessage(role=ChatRole.USER, content="continue"),
    ]
    out = sanitize_tool_call_messages(history)
    roles = [m.role for m in out]
    assert roles == [ChatRole.SYSTEM, ChatRole.USER, ChatRole.ASSISTANT, ChatRole.TOOL, ChatRole.USER]
    assert out[3].tool_call_id == "c1"
    assert out[3].content == MISSING_TOOL_RESULT
    assert out[3].metadata.get("sanitized") is True

    payload = _messages_to_openai(history)
    assert openai_tool_sequence_is_legal(payload)
    assert payload[2]["tool_calls"][0]["id"] == "c1"
    assert payload[3]["role"] == "tool"
    assert payload[3]["tool_call_id"] == "c1"


def test_empty_tool_calls_stripped():
    history = [
        ChatMessage(role=ChatRole.USER, content="hi"),
        ChatMessage(
            role=ChatRole.ASSISTANT,
            content="ok",
            metadata={"tool_calls": []},
        ),
    ]
    out = sanitize_tool_call_messages(history)
    assert out[1].role == ChatRole.ASSISTANT
    assert "tool_calls" not in (out[1].metadata or {})
    payload = _messages_to_openai(history)
    assert "tool_calls" not in payload[1]
    assert openai_tool_sequence_is_legal(payload)


def test_compaction_user_between_tool_calls_and_results_is_repaired():
    history = [
        ChatMessage(role=ChatRole.USER, content="do it"),
        _asst_tools({"id": "c1", "name": "read_file"}),
        ChatMessage(
            role=ChatRole.USER,
            content="[context compacted]",
            metadata={"compacted": True},
        ),
        _tool("c1", "read_file", "file body"),
        ChatMessage(role=ChatRole.USER, content="next"),
    ]
    out = sanitize_tool_call_messages(history)
    assert [m.role for m in out] == [
        ChatRole.USER,
        ChatRole.ASSISTANT,
        ChatRole.TOOL,
        ChatRole.USER,
        ChatRole.USER,
    ]
    assert out[2].tool_call_id == "c1"
    assert out[2].content == "file body"
    assert openai_tool_sequence_is_legal(_messages_to_openai(history))


def test_parallel_session_replay_merged_then_legal():
    """Dispatcher persists one assistant row per tool_call; replay must merge."""
    history = [
        ChatMessage(role=ChatRole.USER, content="search and list"),
        _asst_tools({"id": "c1", "name": "web_search"}),
        _asst_tools({"id": "c2", "name": "list_dir"}),
        _tool("c1", "web_search", "hits"),
        _tool("c2", "list_dir", "files"),
        ChatMessage(role=ChatRole.USER, content="thanks"),
    ]
    out = sanitize_tool_call_messages(history)
    assert out[1].role == ChatRole.ASSISTANT
    ids = [tc["id"] for tc in (out[1].metadata or {}).get("tool_calls") or []]
    assert ids == ["c1", "c2"]
    assert out[2].role == ChatRole.TOOL and out[2].tool_call_id == "c1"
    assert out[3].role == ChatRole.TOOL and out[3].tool_call_id == "c2"
    assert out[4].role == ChatRole.USER
    payload = _messages_to_openai(history)
    assert openai_tool_sequence_is_legal(payload)
    assert len(payload[1]["tool_calls"]) == 2


def test_valid_pair_unchanged():
    history = [
        ChatMessage(role=ChatRole.USER, content="hi"),
        _asst_tools({"id": "c1", "name": "list_dir"}),
        _tool("c1"),
        ChatMessage(role=ChatRole.ASSISTANT, content="done"),
    ]
    out = sanitize_tool_call_messages(history)
    assert [m.role for m in out] == [m.role for m in history]
    assert out[2].content == "ok"
    assert openai_tool_sequence_is_legal(_messages_to_openai(history))
