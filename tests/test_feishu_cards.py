"""Feishu Card JSON 2.0 structure — no live tenant required."""

from __future__ import annotations

import json

from src.adapters.feishu.cards import (
    CARD_CATALOG,
    CARD_JSON_MAX_BYTES,
    CARD_TYPE_ANSWER,
    CARD_TYPE_CHART,
    CARD_TYPE_CONFIRM,
    CARD_TYPE_ERROR,
    CARD_TYPE_SELECT,
    CARD_TYPE_STATS,
    CARD_TYPE_THINKING,
    TEMPLATE_APPROVAL,
    TEMPLATE_ERROR,
    TEMPLATE_NLM,
    TEMPLATE_STREAM,
    build_approval_card,
    build_ask_card,
    build_chart_card,
    build_confirm_card,
    build_error_card,
    build_interactive_card,
    build_kb_pick_card,
    build_no_provider_card,
    build_plan_review_card,
    build_preset_pick_card,
    build_reply_card,
    build_select_card,
    build_session_cleared_card,
    build_stats_card,
    build_streaming_card,
    build_text_card,
    build_thinking_card,
    card_elements,
    card_plain_text,
    default_reply_buttons,
    default_reply_selects,
    extract_citations,
    extract_stats_payload,
    feishu_markdown,
    iter_card_actions,
    iter_select_options,
    sanitize_error,
    summarize_tool_result,
    to_vchart_spec,
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
    joined = card_plain_text(card)
    assert "▌" in joined
    assert "kb_search" in joined
    assert "生成中" in joined or "正在回复" in joined
    think = next(el for el in card_elements(card) if el.get("tag") == "collapsible_panel")
    assert think["expanded"] is True
    assert think["element_id"] == "nlm_think"


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
        selects=default_reply_selects(session_id="feishu:oc_1:ou_1", chat_id="oc_1"),
    )
    _assert_schema_v2(card)
    actions = iter_card_actions(card)
    kinds = {a["action"] for a in actions}
    assert {"retry", "clear", "session_setting"} <= kinds
    retry = next(a for a in actions if a["action"] == "retry")
    assert retry["payload"] == "原始问题"
    assert retry["kind"] == "conversation"
    joined = card_plain_text(card)
    assert "引用来源" in joined
    assert "kb_search" in joined
    think = next(el for el in card_elements(card) if el.get("tag") == "collapsible_panel")
    assert think["expanded"] is False
    opts = {o["option"] for o in iter_select_options(card)}
    assert {"back_providers", "open_preset", "kb:local"} <= opts
    assert any(el.get("tag") == "hr" for el in card_elements(card))
    assert any(el.get("tag") == "column_set" for el in card_elements(card))
    assert any(el.get("tag") == "select_static" for el in card_elements(card))


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


def test_catalog_types_are_registered():
    assert set(CARD_CATALOG) >= {
        CARD_TYPE_THINKING,
        CARD_TYPE_ANSWER,
        CARD_TYPE_SELECT,
        CARD_TYPE_STATS,
        CARD_TYPE_CHART,
        CARD_TYPE_ERROR,
        CARD_TYPE_CONFIRM,
    }


def test_select_card_options_and_callback():
    card = build_select_card(
        title="选择模型",
        markdown="请选择",
        options=[{"label": "GLM-4", "value": "glm-4"}, {"label": "GPT", "value": "gpt"}],
        action="pick_model",
        kind="model_pick",
        session_id="feishu:oc_1:ou_1",
        chat_id="oc_1",
        extra_value={"provider_id": "glm"},
    )
    _assert_schema_v2(card)
    sel = next(el for el in card_elements(card) if el.get("tag") == "select_static")
    values = [o["value"] for o in sel["options"]]
    assert values == ["glm-4", "gpt"]
    assert sel["behaviors"][0]["type"] == "callback"
    assert sel["behaviors"][0]["value"]["action"] == "pick_model"
    assert sel["behaviors"][0]["value"]["provider_id"] == "glm"
    parsed = parse_card_action(
        {
            "header": {"event_type": "card.action.trigger"},
            "event": {
                "operator": {"open_id": "ou_1"},
                "action": {
                    "tag": "select_static",
                    "option": "glm-4",
                    "value": sel["behaviors"][0]["value"],
                },
                "context": {"open_message_id": "om_s", "open_chat_id": "oc_1"},
            },
        }
    )
    assert parsed is not None
    assert parsed.action == "pick_model"
    assert parsed.option == "glm-4"
    assert parsed.model_name == "glm-4"
    assert parsed.provider_id == "glm"


def test_ask_card_uses_select_when_options_overflow():
    opts = [{"id": f"o{i}", "label": f"选项{i}"} for i in range(6)]
    card = build_ask_card(
        call_id="c9",
        title="很多选项",
        questions=[{"id": "q1", "prompt": "选一个", "options": opts}],
    )
    _assert_schema_v2(card)
    sel = next(el for el in card_elements(card) if el.get("tag") == "select_static")
    assert len(sel["options"]) == 6
    assert sel["behaviors"][0]["value"]["question_id"] == "q1"
    parsed = parse_card_action(
        {
            "schema": "2.0",
            "header": {"event_type": "card.action.trigger"},
            "event": {
                "operator": {"open_id": "ou_9"},
                "action": {
                    "tag": "select_static",
                    "option": "o3",
                    "value": sel["behaviors"][0]["value"],
                },
                "context": {"open_message_id": "om_z", "open_chat_id": "oc_1"},
            },
        }
    )
    assert parsed is not None
    assert parsed.answers == {"q1": "o3"}


def test_collapsible_thinking_and_confirm():
    think = build_thinking_card(
        tools=[{"name": "kb_search", "status": "running"}],
        reasoning="先检索文档再回答",
        expanded=True,
    )
    _assert_schema_v2(think)
    panel = next(el for el in card_elements(think) if el.get("tag") == "collapsible_panel")
    assert panel["expanded"] is True
    assert "思考过程" in (panel.get("header") or {}).get("title", {}).get("content", "")
    inner = "\n".join(str(x.get("content") or "") for x in panel.get("elements") or [])
    assert "kb_search" in inner
    assert "先检索" in inner
    confirm = build_confirm_card("确认", "要继续吗？", buttons=[{"label": "OK", "action": "allow"}])
    _assert_schema_v2(confirm)
    assert confirm["header"]["template"] == TEMPLATE_APPROVAL


def test_chart_option_shape_and_echarts_convert():
    spec = to_vchart_spec(
        {
            "title": {"text": "KB"},
            "xAxis": {"data": ["文档", "切片", "已向量"]},
            "series": [{"type": "bar", "data": [3, 12, 8]}],
        }
    )
    assert spec is not None
    assert spec["type"] == "bar"
    assert spec["xField"] == "x"
    assert spec["yField"] == "y"
    assert spec["data"]["values"][0] == {"x": "文档", "y": 3.0}
    pie = to_vchart_spec(
        {"series": [{"type": "pie", "data": [{"name": "A", "value": 1}, {"name": "B", "value": 2}]}]},
        chart_type="pie",
    )
    assert pie is not None
    assert pie["type"] == "pie"
    assert pie["valueField"] == "value"
    native = to_vchart_spec({"type": "line", "data": {"values": [{"x": "t", "y": 1}]}, "xField": "x", "yField": "y"})
    assert native["type"] == "line"
    card = build_chart_card(title="图", option={"xAxis": {"data": ["a"]}, "series": [{"type": "bar", "data": [2]}]})
    _assert_schema_v2(card)
    chart = next(el for el in card_elements(card) if el.get("tag") == "chart")
    assert chart["chart_spec"]["type"] == "bar"
    assert "values" in chart["chart_spec"]["data"]


def test_stats_card_kb_and_fallback_metrics():
    stats = build_stats_card(
        title="知识库统计",
        stats={"kind": "kb_stats", "docs": 4, "chunks": 20, "chunks_with_embedding": 9},
    )
    _assert_schema_v2(stats)
    assert any(el.get("tag") == "chart" for el in card_elements(stats))
    sync = build_stats_card(
        stats={"kind": "kb_sync", "scanned": 10, "added": 3, "updated": 2, "skipped": 5}
    )
    _assert_schema_v2(sync)
    empty = build_chart_card(title="空", option={"series": [{"type": "bar", "data": []}]})
    _assert_schema_v2(empty)
    joined = card_plain_text(empty)
    assert "指标" in joined or "暂无" in joined or "图表" in joined


def test_preset_kb_selects_and_extract_stats():
    preset = build_preset_pick_card(session_id="s", chat_id="oc_1")
    _assert_schema_v2(preset)
    assert {o["option"] for o in iter_select_options(preset)} >= {"read-only", "workspace-write"}
    kb = build_kb_pick_card(session_id="s", chat_id="oc_1", current_kb="kb_demo")
    _assert_schema_v2(kb)
    assert {o["option"] for o in iter_select_options(kb)} >= {"local", "kb_demo"}
    remote = build_kb_pick_card(
        session_id="s",
        chat_id="oc_1",
        current_kb="kb_a",
        remote_kbs=[{"id": "kb_a", "name": "Alpha"}, {"id": "kb_b", "name": "Beta"}],
    )
    _assert_schema_v2(remote)
    assert {o["option"] for o in iter_select_options(remote)} >= {"local", "kb_a", "kb_b"}
    offline = build_kb_pick_card(
        session_id="s",
        chat_id="oc_1",
        offline_note="WeKnora 不可用：offline。可切回本地知识库。",
    )
    assert "WeKnora 不可用" in card_plain_text(offline)
    payload = {
        "name": "kb_stats",
        "success": True,
        "result": {"docs": 2, "chunks": 7, "chunks_with_embedding": 1},
    }
    extracted = extract_stats_payload(payload)
    assert extracted is not None
    assert extracted["kind"] == "kb_stats"
    assert extracted["docs"] == 2
