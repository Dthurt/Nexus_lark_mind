"""Feishu Card JSON 2.0 structure — no live tenant required."""

from __future__ import annotations

import json

from src.adapters.feishu.cards import (
    CARD_JSON_MAX_BYTES,
    TEMPLATE_APPROVAL,
    TEMPLATE_ERROR,
    TEMPLATE_NLM,
    TEMPLATE_STREAM,
    build_approval_card,
    build_ask_card,
    build_error_card,
    build_interactive_card,
    build_no_provider_card,
    build_plan_review_card,
    build_reply_card,
    build_session_cleared_card,
    build_streaming_card,
    build_text_card,
    card_elements,
    default_reply_buttons,
    extract_citations,
    feishu_markdown,
    iter_card_actions,
    sanitize_error,
    summarize_tool_result,
)
from src.adapters.feishu.events import classify_payload, parse_card_action


def _assert_schema_v2(card: dict) -> None:
    assert card["schema"] == "2.0"
    assert "body" in card
    assert isinstance(card["body"]["elements"], list)
    assert card["header"]["title"]["tag"] == "plain_text"
    assert card["header"]["template"]
    assert "elements" not in card or "body" in card
    raw = json.dumps(card, ensure_ascii=False)
    assert len(raw.encode("utf-8")) <= CARD_JSON_MAX_BYTES


def test_text_card_is_schema_2():
    card = build_text_card("Nexus Lark Mind", "hello **world**")
    _assert_schema_v2(card)
    assert card["header"]["template"] == TEMPLATE_NLM
    els = card_elements(card)
    assert any(el.get("tag") == "markdown" and "hello" in el.get("content", "") for el in els)
    assert not any(el.get("tag") == "div" for el in els)


def test_streaming_card_cursor_and_note():
    card = build_streaming_card(
        "Nexus Lark Mind",
        "partial",
        status="生成中…",
        user_preview="帮我查文档",
        tools=[{"name": "kb_search", "status": "running"}],
    )
    _assert_schema_v2(card)
    assert card["header"]["template"] == TEMPLATE_STREAM
    assert card["config"]["streaming_mode"] is True
    joined = "\n".join(str(el.get("content") or "") for el in card_elements(card))
    assert "▌" in joined
    assert "kb_search" in joined
    assert "生成中" in joined or "正在回复" in joined


def test_reply_card_citations_and_buttons():
    card = build_reply_card(
        "答案见上文",
        citations="- **README.md** — 本地知识库",
        tools=[{"name": "kb_search", "status": "ok", "summary": "2 条命中"}],
        buttons=default_reply_buttons(
            session_id="feishu:oc_1:ou_1",
            chat_id="oc_1",
            retry_text="原始问题",
        ),
    )
    _assert_schema_v2(card)
    actions = iter_card_actions(card)
    kinds = {a["action"] for a in actions}
    assert {"retry", "clear", "back_providers"} <= kinds
    retry = next(a for a in actions if a["action"] == "retry")
    assert retry["payload"] == "原始问题"
    assert retry["kind"] == "conversation"
    joined = "\n".join(str(el.get("content") or "") for el in card_elements(card))
    assert "引用来源" in joined
    assert any(el.get("tag") == "hr" for el in card_elements(card))
    assert any(el.get("tag") == "column_set" for el in card_elements(card))


def test_error_card_strips_traceback():
    raw = (
        'Traceback (most recent call last):\n'
        '  File "runner.py", line 1, in <module>\n'
        "    boom()\n"
        "ValueError: 模型超时"
    )
    card = build_error_card(raw, buttons=[{"label": "重试", "action": "retry", "kind": "conversation"}])
    _assert_schema_v2(card)
    assert card["header"]["template"] == TEMPLATE_ERROR
    joined = "\n".join(str(el.get("content") or "") for el in card_elements(card))
    assert "Traceback" not in joined
    assert "runner.py" not in joined
    assert "模型超时" in joined


def test_sanitize_error_and_rate_limit_card():
    assert "Traceback" not in sanitize_error("Traceback (most recent call last):\nboom")
    card = build_error_card("429 限流，请稍后", rate_limited=True)
    assert card["header"]["template"] == "yellow"
    joined = "\n".join(str(el.get("content") or "") for el in card_elements(card))
    assert "限流" in joined


def test_approval_card_callbacks():
    card = build_approval_card(
        call_id="c1",
        name="run_shell",
        base="run_shell",
        arguments={"cmd": "ls"},
    )
    _assert_schema_v2(card)
    assert card["header"]["template"] == TEMPLATE_APPROVAL
    actions = iter_card_actions(card)
    assert {a["action"] for a in actions} == {"allow", "allow_session", "deny"}
    assert all(a["kind"] == "approval" and a["call_id"] == "c1" for a in actions)
    # Schema 2.0 buttons expose behaviors.callback
    buttons = []
    for el in card_elements(card):
        if el.get("tag") == "column_set":
            for col in el.get("columns") or []:
                buttons.extend(col.get("elements") or [])
    assert buttons
    assert buttons[0]["behaviors"][0]["type"] == "callback"
    assert buttons[0]["value"]["action"] == buttons[0]["behaviors"][0]["value"]["action"]


def test_ask_and_plan_and_setup_cards():
    ask = build_ask_card(
        call_id="c2",
        title="选择",
        questions=[{"id": "q1", "prompt": "用哪套？", "options": [{"id": "a", "label": "A"}]}],
    )
    _assert_schema_v2(ask)
    plan = build_plan_review_card(call_id="pr", title="Plan", plan="# hi\n```python\nprint(1)\n```")
    _assert_schema_v2(plan)
    setup = build_no_provider_card()
    _assert_schema_v2(setup)
    cleared = build_session_cleared_card()
    _assert_schema_v2(cleared)


def test_oversized_markdown_is_truncated():
    huge = "字" * 50_000
    card = build_interactive_card(title="NLM", markdown=huge)
    _assert_schema_v2(card)
    raw = json.dumps(card, ensure_ascii=False)
    assert len(raw.encode("utf-8")) <= CARD_JSON_MAX_BYTES


def test_feishu_markdown_fences_json_dumps():
    md = feishu_markdown('{"ok": true, "hits": 2}')
    assert md.startswith("```json")
    assert "ok" in md


def test_extract_citations_and_tool_summary():
    payload = {
        "name": "kb_search",
        "success": True,
        "result": {
            "citations_md": "- **a.md**",
            "results": [{"title": "a.md"}, {"title": "b.md"}],
        },
    }
    assert "**a.md**" in extract_citations(payload)
    status, summary = summarize_tool_result(payload)
    assert status == "ok"
    assert "2" in summary


def test_parse_schema2_card_action_trigger():
    payload = {
        "schema": "2.0",
        "header": {"event_type": "card.action.trigger"},
        "event": {
            "operator": {"open_id": "ou_9"},
            "action": {
                "tag": "button",
                "value": {
                    "action": "retry",
                    "kind": "conversation",
                    "payload": "原始问题",
                    "session_id": "feishu:oc_1:ou_9",
                },
            },
            "context": {"open_message_id": "om_z", "open_chat_id": "oc_1"},
        },
    }
    parsed = parse_card_action(payload)
    assert parsed is not None
    assert parsed.action == "retry"
    assert parsed.kind == "conversation"
    assert parsed.open_message_id == "om_z"
    assert parsed.chat_id == "oc_1"
    assert parsed.user_id == "ou_9"
    kind, data = classify_payload(payload)
    assert kind == "card_action"
    assert data.payload == "原始问题"
