"""Feishu / Lark interactive cards — Card JSON schema 2.0 (Card Kit).

Sent as ``msg_type=interactive`` via ``im.v1/messages``. Callbacks use
``behaviors.callback.value`` (and a legacy ``value`` mirror) so
``card.action.trigger`` keeps working for long-connection and webhook.

Limits we respect (Open Platform, interactive message body):
- ~30 KB JSON per card (we stay under ~28 KB)
- Markdown subset + code fences; no HTML dumps / stack traces
- Button labels short; callback value stays small
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# IM interactive content is documented at 30 KB; keep headroom for wrapping.
CARD_JSON_MAX_BYTES = 28_000
MARKDOWN_MAX_CHARS = 10_000
CODE_PREVIEW_MAX = 600
CITATION_MAX_CHARS = 1_600
ERROR_MAX_CHARS = 480
MAX_TOOL_ROWS = 8
MAX_BUTTONS = 6
MAX_BUTTON_LABEL = 40
MAX_SELECT_OPTIONS = 40
MAX_CHART_POINTS = 12
REASONING_MAX_CHARS = 1_600
CHART_SPEC_MAX_BYTES = 3_600

TEMPLATE_NLM = "indigo"
TEMPLATE_STREAM = "blue"
TEMPLATE_KB = "turquoise"
TEMPLATE_TOOL = "violet"
TEMPLATE_APPROVAL = "orange"
TEMPLATE_ASK = "purple"
TEMPLATE_PLAN = "carmine"
TEMPLATE_ERROR = "red"
TEMPLATE_WARN = "yellow"
TEMPLATE_OK = "green"
TEMPLATE_SETUP = "wathet"
TEMPLATE_STATS = "carmine"

# Catalog type names used by the channel (not sent to Feishu).
CARD_TYPE_THINKING = "thinking"
CARD_TYPE_ANSWER = "answer"
CARD_TYPE_SELECT = "select"
CARD_TYPE_STATS = "stats"
CARD_TYPE_CHART = "chart"
CARD_TYPE_ERROR = "error"
CARD_TYPE_CONFIRM = "confirm"


def truncate(text: str, limit: int, *, suffix: str = "…") -> str:
    raw = text or ""
    if limit <= 0 or len(raw) <= limit:
        return raw
    keep = max(0, limit - len(suffix))
    return raw[:keep] + suffix


def sanitize_error(text: str, *, limit: int = ERROR_MAX_CHARS) -> str:
    """User-facing error: drop tracebacks / hex dumps, cap length."""
    raw = (text or "unknown error").strip() or "unknown error"
    kept: List[str] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("Traceback") or stripped.startswith("The above exception"):
            continue
        if stripped.startswith("During handling of"):
            continue
        if stripped.startswith("File ") or 'File "' in stripped:
            continue
        if stripped.startswith("at 0x") or re.search(r"0x[0-9a-fA-F]{6,}", stripped):
            continue
        kept.append(stripped)
    cleaned = "\n".join(kept).strip() or "发生未知错误"
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    return truncate(cleaned, limit)


def _preview_args(arguments: Any, limit: int = CODE_PREVIEW_MAX) -> str:
    try:
        text = json.dumps(arguments or {}, ensure_ascii=False, indent=2)
    except Exception:
        text = str(arguments or "")
    return truncate(text, limit, suffix="\n…")


def _fence(body: str, lang: str = "") -> str:
    inner = (body or "").replace("```", "'''")
    return f"```{lang}\n{inner}\n```"


def feishu_markdown(content: str, *, limit: int = MARKDOWN_MAX_CHARS) -> str:
    """Normalize assistant text for Feishu markdown 2.0 (code / images / lists)."""
    text = (content or "").replace("\r\n", "\n").strip()
    if not text:
        return ""
    stripped = text.lstrip()
    if stripped[:1] in "{[" and not stripped.startswith("```"):
        try:
            parsed = json.loads(stripped)
        except Exception:
            parsed = None
        if parsed is not None:
            try:
                text = _fence(json.dumps(parsed, ensure_ascii=False, indent=2), "json")
            except Exception:
                text = _fence(stripped, "json")
    return truncate(text, limit)


def _plain(content: str) -> Dict[str, str]:
    return {"tag": "plain_text", "content": content or ""}


def _markdown_el(
    content: str,
    *,
    element_id: str = "",
    text_size: str = "normal",
    icon_token: str = "",
) -> Dict[str, Any]:
    el: Dict[str, Any] = {
        "tag": "markdown",
        "content": content or " ",
        "text_align": "left",
        "text_size": text_size,
    }
    if element_id:
        el["element_id"] = element_id[:20]
    if icon_token:
        el["icon"] = {"tag": "standard_icon", "token": icon_token}
    return el


def _hr() -> Dict[str, str]:
    return {"tag": "hr"}


def _button(btn: Dict[str, Any], *, element_id: str = "") -> Dict[str, Any]:
    value: Dict[str, Any] = {
        "action": btn.get("action", "noop"),
        "payload": btn.get("payload", ""),
    }
    if btn.get("kind"):
        value["kind"] = btn["kind"]
    if btn.get("call_id"):
        value["call_id"] = btn["call_id"]
    if btn.get("answers") is not None:
        value["answers"] = btn["answers"]
    for key in (
        "provider_id",
        "model_name",
        "session_id",
        "chat_id",
        "page",
    ):
        if btn.get(key) is not None and btn.get(key) != "":
            value[key] = btn[key]
    label = truncate(str(btn.get("label") or "OK"), MAX_BUTTON_LABEL)
    el: Dict[str, Any] = {
        "tag": "button",
        "text": _plain(label),
        "type": btn.get("type") or "primary",
        "width": btn.get("width") or "default",
        "size": btn.get("size") or "medium",
        "behaviors": [{"type": "callback", "value": value}],
        "value": value,
    }
    if element_id:
        el["element_id"] = element_id[:20]
    confirm = btn.get("confirm")
    if isinstance(confirm, dict) and confirm.get("title"):
        el["confirm"] = {
            "title": _plain(str(confirm.get("title") or "确认")),
            "text": _plain(str(confirm.get("text") or "")),
        }
    return el


def _button_row(buttons: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not buttons:
        return []
    cols: List[Dict[str, Any]] = []
    for i, btn in enumerate(list(buttons)[:MAX_BUTTONS]):
        cols.append(
            {
                "tag": "column",
                "width": "weighted",
                "weight": 1,
                "vertical_align": "top",
                "elements": [_button(btn, element_id=f"btn_{i}_{btn.get('action', 'x')}"[:20])],
            }
        )
    return [
        {
            "tag": "column_set",
            "flex_mode": "flow",
            "background_style": "default",
            "horizontal_spacing": "8px",
            "horizontal_align": "left",
            "columns": cols,
        }
    ]


def _callback_value(data: Dict[str, Any]) -> Dict[str, Any]:
    value: Dict[str, Any] = {
        "action": data.get("action", "noop"),
        "payload": data.get("payload", ""),
    }
    if data.get("kind"):
        value["kind"] = data["kind"]
    if data.get("call_id"):
        value["call_id"] = data["call_id"]
    if data.get("answers") is not None:
        value["answers"] = data["answers"]
    if data.get("question_id"):
        value["question_id"] = data["question_id"]
    for key in (
        "provider_id",
        "model_name",
        "session_id",
        "chat_id",
        "page",
        "permission_preset",
        "kb_id",
    ):
        if data.get(key) is not None and data.get(key) != "":
            value[key] = data[key]
    return value


def _select_static(
    spec: Dict[str, Any],
    *,
    element_id: str = "nlm_select",
) -> Dict[str, Any]:
    """Official Card Kit 2.0 ``select_static`` / ``multi_select_static``."""
    options: List[Dict[str, Any]] = []
    for opt in list(spec.get("options") or [])[:MAX_SELECT_OPTIONS]:
        if not isinstance(opt, dict):
            continue
        oid = str(opt.get("value") or opt.get("id") or "").strip()
        label = truncate(str(opt.get("label") or oid), MAX_BUTTON_LABEL)
        if not oid:
            continue
        item: Dict[str, Any] = {
            "text": _plain(label),
            "value": oid[:200],
        }
        if opt.get("icon_token"):
            item["icon"] = {"tag": "standard_icon", "token": str(opt["icon_token"])}
        options.append(item)
    value = _callback_value(spec)
    multi = bool(spec.get("multi"))
    el: Dict[str, Any] = {
        "tag": "multi_select_static" if multi else "select_static",
        "element_id": (element_id or "nlm_select")[:20],
        "placeholder": _plain(str(spec.get("placeholder") or "请选择")),
        "width": spec.get("width") or "fill",
        "type": spec.get("type") or "default",
        "options": options,
        "behaviors": [{"type": "callback", "value": value}],
        "value": value,
    }
    initial = str(spec.get("initial") or spec.get("initial_option") or "")
    if initial and not multi:
        el["initial_option"] = initial
    return el


def _overflow(spec: Dict[str, Any], *, element_id: str = "nlm_more") -> Dict[str, Any]:
    """Overflow menu when a handful of extra actions would overflow a button row."""
    options: List[Dict[str, Any]] = []
    for opt in list(spec.get("options") or [])[:MAX_SELECT_OPTIONS]:
        if not isinstance(opt, dict):
            continue
        oid = str(opt.get("value") or opt.get("id") or "").strip()
        label = truncate(str(opt.get("label") or oid), MAX_BUTTON_LABEL)
        if not oid:
            continue
        options.append({"text": _plain(label), "value": oid[:200]})
    value = _callback_value(spec)
    return {
        "tag": "overflow",
        "element_id": (element_id or "nlm_more")[:20],
        "options": options,
        "behaviors": [{"type": "callback", "value": value}],
        "value": value,
    }


def _collapsible_panel(
    *,
    title: str,
    elements: Sequence[Dict[str, Any]],
    expanded: bool = False,
    element_id: str = "nlm_fold",
    icon_token: str = "down-small-ccm_outlined",
) -> Dict[str, Any]:
    """Official Card Kit 2.0 ``collapsible_panel`` (no form children)."""
    return {
        "tag": "collapsible_panel",
        "element_id": (element_id or "nlm_fold")[:20],
        "expanded": bool(expanded),
        "direction": "vertical",
        "vertical_spacing": "8px",
        "padding": "8px 8px 8px 8px",
        "header": {
            "title": {"tag": "markdown", "content": f"**{truncate(title, 40)}**"},
            "vertical_align": "center",
            "icon": {
                "tag": "standard_icon",
                "token": icon_token,
                "size": "16px 16px",
            },
            "icon_position": "right",
            "icon_expanded_angle": -180,
        },
        "border": {"color": "grey", "corner_radius": "5px"},
        "elements": [dict(el) for el in elements if el],
    }


def _metric_columns(metrics: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    rows = [m for m in metrics if isinstance(m, dict) and (m.get("label") or m.get("value") is not None)]
    if not rows:
        return None
    cols: List[Dict[str, Any]] = []
    for i, item in enumerate(rows[:4]):
        label = truncate(str(item.get("label") or ""), 16)
        value = truncate(str(item.get("value") if item.get("value") is not None else "—"), 18)
        cols.append(
            {
                "tag": "column",
                "width": "weighted",
                "weight": 1,
                "vertical_align": "top",
                "elements": [
                    _markdown_el(f"**{value}**\n{label}", element_id=f"nlm_m{i}"[:20], text_size="small")
                ],
            }
        )
    return {
        "tag": "column_set",
        "flex_mode": "stretch",
        "background_style": "grey",
        "horizontal_spacing": "8px",
        "horizontal_align": "left",
        "columns": cols,
    }


def to_vchart_spec(
    option: Optional[Dict[str, Any]],
    *,
    chart_type: str = "bar",
) -> Optional[Dict[str, Any]]:
    """Accept VChart spec or a small ECharts option; keep payload tiny."""
    if not isinstance(option, dict) or not option:
        return None
    if option.get("type") and isinstance(option.get("data"), dict) and "values" in (option.get("data") or {}):
        spec = dict(option)
        values = list((spec.get("data") or {}).get("values") or [])[:MAX_CHART_POINTS]
        spec["data"] = {"values": values}
        raw = json.dumps(spec, ensure_ascii=False)
        if len(raw.encode("utf-8")) > CHART_SPEC_MAX_BYTES:
            return None
        return spec

    kind = str(chart_type or option.get("type") or "").strip().lower()
    series = option.get("series") if isinstance(option.get("series"), list) else []
    first = series[0] if series and isinstance(series[0], dict) else {}
    if not kind:
        kind = str(first.get("type") or "bar").strip().lower()
    if kind not in {"bar", "line", "pie"}:
        kind = "bar"

    if kind == "pie":
        raw_points = first.get("data") or option.get("data") or []
        values: List[Dict[str, Any]] = []
        if isinstance(raw_points, list):
            for item in raw_points[:MAX_CHART_POINTS]:
                if isinstance(item, dict):
                    name = str(item.get("name") or item.get("x") or "")
                    try:
                        val = float(item.get("value") if item.get("value") is not None else item.get("y") or 0)
                    except (TypeError, ValueError):
                        continue
                    if name:
                        values.append({"name": truncate(name, 24), "value": val})
        if not values:
            return None
        spec = {
            "type": "pie",
            "data": {"values": values},
            "valueField": "value",
            "categoryField": "name",
        }
    else:
        cats = []
        xaxis = option.get("xAxis") if isinstance(option.get("xAxis"), dict) else {}
        if isinstance(xaxis.get("data"), list):
            cats = [str(x) for x in xaxis["data"]]
        elif isinstance(option.get("categories"), list):
            cats = [str(x) for x in option["categories"]]
        nums = first.get("data") if isinstance(first.get("data"), list) else option.get("values")
        if not isinstance(nums, list):
            nums = []
        values = []
        for i, num in enumerate(list(nums)[:MAX_CHART_POINTS]):
            label = cats[i] if i < len(cats) else str(i + 1)
            try:
                y = float(num)
            except (TypeError, ValueError):
                continue
            values.append({"x": truncate(label, 20), "y": y})
        if not values:
            return None
        spec = {
            "type": kind,
            "data": {"values": values},
            "xField": "x",
            "yField": "y",
        }
    title = option.get("title")
    if isinstance(title, dict) and title.get("text"):
        spec["title"] = {"text": truncate(str(title["text"]), 40)}
    elif isinstance(title, str) and title.strip():
        spec["title"] = {"text": truncate(title.strip(), 40)}
    raw = json.dumps(spec, ensure_ascii=False)
    if len(raw.encode("utf-8")) > CHART_SPEC_MAX_BYTES:
        return None
    return spec


def _chart_el(
    spec: Optional[Dict[str, Any]],
    *,
    element_id: str = "nlm_chart",
    aspect_ratio: str = "16:9",
) -> Optional[Dict[str, Any]]:
    if not spec:
        return None
    return {
        "tag": "chart",
        "element_id": (element_id or "nlm_chart")[:20],
        "aspect_ratio": aspect_ratio,
        "color_theme": "brand",
        "preview": True,
        "height": "auto",
        "chart_spec": spec,
    }


def _note_el(text: str, *, element_id: str = "nlm_note") -> Dict[str, Any]:
    inner = (text or "").replace("\n", "<br/>")
    return _markdown_el(f"<note icon='true'>{inner}</note>", element_id=element_id)


def _walk_nodes(node: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(node, list):
        for item in node:
            yield from _walk_nodes(item)
        return
    if not isinstance(node, dict):
        return
    yield node
    yield from _walk_nodes(node.get("elements") or [])
    if node.get("tag") == "column_set":
        for col in node.get("columns") or []:
            yield from _walk_nodes((col or {}).get("elements") or [])


def _shrink_markdown_nodes(elements: Sequence[Dict[str, Any]], limit: int) -> None:
    for el in _walk_nodes(list(elements)):
        if isinstance(el, dict) and el.get("tag") == "markdown":
            el["content"] = truncate(str(el.get("content") or ""), limit)


def _drop_heavy_extras(elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    kept: List[Dict[str, Any]] = []
    for el in elements:
        if not isinstance(el, dict):
            continue
        if el.get("tag") == "chart":
            continue
        if el.get("tag") == "collapsible_panel":
            inner = list(el.get("elements") or [])
            _shrink_markdown_nodes(inner, 600)
            el["elements"] = inner[:2]
        kept.append(el)
    return kept


def _fit_card(card: Dict[str, Any]) -> Dict[str, Any]:
    raw = json.dumps(card, ensure_ascii=False)
    if len(raw.encode("utf-8")) <= CARD_JSON_MAX_BYTES:
        return card
    body = card.get("body") or {}
    elements = list(body.get("elements") or [])
    _shrink_markdown_nodes(elements, 4_000)
    body["elements"] = elements[:14]
    card["body"] = body
    raw = json.dumps(card, ensure_ascii=False)
    if len(raw.encode("utf-8")) > CARD_JSON_MAX_BYTES:
        elements = _drop_heavy_extras(elements)
        _shrink_markdown_nodes(elements, 1_800)
        body["elements"] = elements[:10]
        card["body"] = body
    return card


def build_interactive_card(
    *,
    title: str,
    markdown: str = "",
    subtitle: str = "",
    template: str = TEMPLATE_NLM,
    icon_token: str = "chat-outlined",
    buttons: Optional[Sequence[Dict[str, Any]]] = None,
    extra_elements: Optional[Sequence[Dict[str, Any]]] = None,
    prepend_elements: Optional[Sequence[Dict[str, Any]]] = None,
    selects: Optional[Sequence[Dict[str, Any]]] = None,
    streaming: bool = False,
    element_id: str = "nlm_body",
) -> Dict[str, Any]:
    """Canonical Card JSON 2.0 builder."""
    elements: List[Dict[str, Any]] = []
    for extra in prepend_elements or []:
        if extra:
            elements.append(dict(extra))
    body_md = feishu_markdown(markdown) if markdown else ""
    if body_md:
        elements.append(_markdown_el(body_md, element_id=element_id or "nlm_body"))
    for extra in extra_elements or []:
        if extra:
            elements.append(dict(extra))
    if selects:
        if elements:
            elements.append(_hr())
        for i, spec in enumerate(list(selects)[:3]):
            if spec:
                elements.append(_select_static(spec, element_id=f"nlm_sel_{i}"[:20]))
    if buttons:
        if elements:
            elements.append(_hr())
        elements.extend(_button_row(buttons))
    if not elements:
        elements.append(_markdown_el("…", element_id="nlm_empty"))

    header: Dict[str, Any] = {
        "title": _plain(truncate(title, 50)),
        "template": template or TEMPLATE_NLM,
        "padding": "12px 12px 12px 12px",
    }
    if subtitle:
        header["subtitle"] = _plain(truncate(subtitle, 80))
    if icon_token:
        header["icon"] = {"tag": "standard_icon", "token": icon_token}

    card: Dict[str, Any] = {
        "schema": "2.0",
        "config": {
            "update_multi": True,
            "width_mode": "fill",
            "enable_forward": True,
            "streaming_mode": bool(streaming),
        },
        "header": header,
        "body": {
            "direction": "vertical",
            "padding": "12px 12px 12px 12px",
            "vertical_spacing": "8px",
            "elements": elements,
        },
    }
    return _fit_card(card)


def card_elements(card: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not isinstance(card, dict):
        return []
    if str(card.get("schema") or "") == "2.0":
        return list((card.get("body") or {}).get("elements") or [])
    return list(card.get("elements") or [])


def iter_card_actions(card: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Callback value dicts from schema 2.0 buttons or schema 1.0 action groups."""
    values: List[Dict[str, Any]] = []

    def walk(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        if not isinstance(node, dict):
            return
        tag = node.get("tag")
        if tag in {"button", "select_static", "multi_select_static", "overflow"}:
            seen = False
            for beh in node.get("behaviors") or []:
                if isinstance(beh, dict) and isinstance(beh.get("value"), dict):
                    values.append(beh["value"])
                    seen = True
            if not seen and isinstance(node.get("value"), dict):
                values.append(node["value"])
        if tag == "action":
            walk(node.get("actions") or [])
        if tag == "column_set":
            for col in node.get("columns") or []:
                walk((col or {}).get("elements") or [])
        walk(node.get("elements") or [])

    walk(card_elements(card))
    return values


def iter_select_options(card: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Flatten select / overflow options with their callback value."""
    out: List[Dict[str, Any]] = []
    for node in _walk_nodes(card_elements(card)):
        tag = node.get("tag")
        if tag not in {"select_static", "multi_select_static", "overflow"}:
            continue
        value = {}
        for beh in node.get("behaviors") or []:
            if isinstance(beh, dict) and isinstance(beh.get("value"), dict):
                value = beh["value"]
                break
        if not value and isinstance(node.get("value"), dict):
            value = node["value"]
        for opt in node.get("options") or []:
            if not isinstance(opt, dict):
                continue
            text = ""
            if isinstance(opt.get("text"), dict):
                text = str(opt["text"].get("content") or "")
            out.append(
                {
                    "tag": tag,
                    "label": text,
                    "option": str(opt.get("value") or ""),
                    "action": value.get("action"),
                    "kind": value.get("kind"),
                    "value": value,
                }
            )
    return out


def card_plain_text(card: Dict[str, Any]) -> str:
    """Join all markdown / plain_text content, including folded panels."""
    chunks: List[str] = []
    for node in _walk_nodes(card_elements(card)):
        if not isinstance(node, dict):
            continue
        if node.get("tag") == "markdown":
            chunks.append(str(node.get("content") or ""))
        title = (node.get("header") or {}).get("title") if isinstance(node.get("header"), dict) else None
        if isinstance(title, dict):
            chunks.append(str(title.get("content") or ""))
    return "\n".join(chunks)


def build_text_card(
    title: str,
    content: str,
    *,
    buttons: Optional[List[Dict[str, Any]]] = None,
    template: str = TEMPLATE_NLM,
    subtitle: str = "对话",
    icon_token: str = "chat-outlined",
    extra_elements: Optional[Sequence[Dict[str, Any]]] = None,
    streaming: bool = False,
) -> Dict[str, Any]:
    return build_interactive_card(
        title=title,
        markdown=content,
        subtitle=subtitle,
        template=template,
        icon_token=icon_token,
        buttons=buttons,
        extra_elements=extra_elements,
        streaming=streaming,
    )


def _tool_markdown(tools: Sequence[Dict[str, Any]]) -> str:
    if not tools:
        return ""
    lines = ["**工具**"]
    for item in list(tools)[:MAX_TOOL_ROWS]:
        name = str(item.get("name") or item.get("base") or "tool").strip() or "tool"
        status = str(item.get("status") or "running")
        mark = {"running": "⏳", "ok": "✅", "error": "❌"}.get(status, "•")
        summary = str(item.get("summary") or "").strip()
        line = f"- {mark} `{name}`"
        if summary:
            line += f"  {truncate(summary, 80)}"
        lines.append(line)
    extra = len(tools) - MAX_TOOL_ROWS
    if extra > 0:
        lines.append(f"- …另有 {extra} 项")
    return "\n".join(lines)


def _thinking_title(tools: Sequence[Dict[str, Any]], *, streaming: bool) -> str:
    running = sum(1 for t in tools if str(t.get("status") or "") == "running")
    n = len(list(tools or []))
    if streaming and running:
        return f"思考过程 · {running} 个工具 ⏳"
    if n:
        return f"思考过程 · {n} 个工具"
    return "思考过程"


def build_thinking_elements(
    *,
    tools: Optional[Sequence[Dict[str, Any]]] = None,
    reasoning: str = "",
    expanded: bool = False,
    streaming: bool = False,
) -> List[Dict[str, Any]]:
    """Folded 思考过程: tools + optional model reasoning. Expand to inspect."""
    tool_md = _tool_markdown(tools or [])
    think = truncate((reasoning or "").strip(), REASONING_MAX_CHARS)
    if not tool_md and not think:
        return []
    chunks: List[str] = []
    if think:
        chunks.append("**推理**\n\n" + think)
    if tool_md:
        chunks.append(tool_md)
    panel = _collapsible_panel(
        title=_thinking_title(tools or [], streaming=streaming),
        elements=[_markdown_el("\n\n".join(chunks), element_id="nlm_think_md")],
        expanded=expanded,
        element_id="nlm_think",
        icon_token="down-small-ccm_outlined",
    )
    return [panel]


def build_thinking_card(
    *,
    tools: Optional[Sequence[Dict[str, Any]]] = None,
    reasoning: str = "",
    status: str = "",
    user_preview: str = "",
    expanded: bool = True,
) -> Dict[str, Any]:
    """Standalone thinking catalog card (streaming fold)."""
    prepend = build_thinking_elements(
        tools=tools,
        reasoning=reasoning,
        expanded=expanded,
        streaming=True,
    )
    if status or user_preview:
        notes = []
        if user_preview:
            notes.append(f"正在回复：**{truncate(user_preview, 80)}**")
        if status:
            notes.append(status)
        prepend = [_note_el("<br/>".join(notes), element_id="nlm_note")] + prepend
    if not prepend:
        prepend = [_note_el("生成中…", element_id="nlm_note")]
    return build_interactive_card(
        title="思考过程",
        markdown="",
        subtitle="可展开查看",
        template=TEMPLATE_STREAM,
        icon_token="todo-outlined",
        prepend_elements=prepend,
        streaming=True,
        element_id="nlm_think_c",
    )


def _citation_elements(citations: str) -> List[Dict[str, Any]]:
    cite = truncate((citations or "").strip(), CITATION_MAX_CHARS)
    if not cite:
        return []
    return [
        _hr(),
        _markdown_el("**引用来源**\n\n" + cite, element_id="nlm_cites", icon_token="file-outlined"),
    ]


def _stats_elements(
    stats: Optional[Dict[str, Any]] = None,
    usage: Optional[Dict[str, Any]] = None,
    *,
    prefer_chart: bool = True,
) -> List[Dict[str, Any]]:
    extras: List[Dict[str, Any]] = []
    chart_el, metrics = stats_to_visuals(stats, usage)
    if prefer_chart and chart_el:
        extras.append(_hr())
        extras.append(chart_el)
    if metrics:
        cols = _metric_columns(metrics)
        if cols:
            if not extras:
                extras.append(_hr())
            extras.append(cols)
    return extras


def build_streaming_card(
    title: str,
    content: str,
    *,
    status: str = "",
    tools: Optional[Sequence[Dict[str, Any]]] = None,
    user_preview: str = "",
    citations: str = "",
    reasoning: str = "",
) -> Dict[str, Any]:
    prepend: List[Dict[str, Any]] = []
    notes: List[str] = []
    preview = truncate((user_preview or "").strip(), 80)
    if preview:
        notes.append(f"正在回复：**{preview}**")
    status_text = (status or "").strip()
    if status_text:
        notes.append(status_text)
    elif not (content or "").strip() and not tools and not reasoning:
        notes.append("生成中…")
    if notes:
        prepend.append(_note_el("<br/>".join(notes), element_id="nlm_note"))
    prepend.extend(
        build_thinking_elements(
            tools=tools,
            reasoning=reasoning,
            expanded=True,
            streaming=True,
        )
    )
    extras = _citation_elements(citations)
    body = feishu_markdown(content)
    if body:
        body = body + " ▌"
    elif not prepend and not extras:
        body = "生成中… ▌"
    return build_interactive_card(
        title=title or "Nexus Lark Mind",
        markdown=body,
        subtitle="生成中",
        template=TEMPLATE_STREAM,
        icon_token="chat-outlined",
        prepend_elements=prepend,
        extra_elements=extras,
        streaming=True,
        element_id="nlm_stream",
    )


def build_reply_card(
    content: str,
    *,
    title: str = "Nexus Lark Mind",
    citations: str = "",
    tools: Optional[Sequence[Dict[str, Any]]] = None,
    buttons: Optional[List[Dict[str, Any]]] = None,
    selects: Optional[Sequence[Dict[str, Any]]] = None,
    user_preview: str = "",
    reasoning: str = "",
    stats: Optional[Dict[str, Any]] = None,
    usage: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    extras: List[Dict[str, Any]] = []
    extras.extend(
        build_thinking_elements(
            tools=tools,
            reasoning=reasoning,
            expanded=False,
            streaming=False,
        )
    )
    extras.extend(_citation_elements(citations))
    extras.extend(_stats_elements(stats, usage))
    cite = truncate((citations or "").strip(), CITATION_MAX_CHARS)
    subtitle = "知识库" if cite else "对话"
    template = TEMPLATE_KB if cite else TEMPLATE_NLM
    preview = truncate((user_preview or "").strip(), 60)
    if preview:
        subtitle = f"{subtitle} · {preview}"
    return build_interactive_card(
        title=title,
        markdown=content or "（空回复）",
        subtitle=subtitle,
        template=template,
        icon_token="file-outlined" if cite else "chat-outlined",
        buttons=buttons,
        selects=selects,
        extra_elements=extras,
        streaming=False,
        element_id="nlm_reply",
    )


def build_error_card(
    error: str,
    *,
    title: str = "任务失败",
    buttons: Optional[List[Dict[str, Any]]] = None,
    rate_limited: bool = False,
) -> Dict[str, Any]:
    detail = sanitize_error(error)
    if rate_limited:
        note = "模型暂时限流，稍后再试或点「再问一次」。"
        body = f"**这次没有完成**\n\n{detail}"
        template = TEMPLATE_WARN
        subtitle = "限流"
        icon = "warning-outlined"
    else:
        note = "回复中断。可重试，或换一个模型再问。"
        body = f"**这次回复没有完成**\n\n{detail}"
        template = TEMPLATE_ERROR
        subtitle = "错误"
        icon = "close-outlined"
    return build_interactive_card(
        title=title,
        markdown=body,
        subtitle=subtitle,
        template=template,
        icon_token=icon,
        buttons=buttons,
        prepend_elements=[_note_el(note, element_id="nlm_err_note")],
        streaming=False,
        element_id="nlm_error",
    )


def build_confirm_card(
    title: str,
    content: str,
    *,
    buttons: Optional[Sequence[Dict[str, Any]]] = None,
    subtitle: str = "请确认",
    template: str = TEMPLATE_APPROVAL,
) -> Dict[str, Any]:
    return build_interactive_card(
        title=title or "请确认",
        markdown=content or "请确认后再继续。",
        subtitle=subtitle,
        template=template,
        icon_token="warning-outlined",
        buttons=buttons,
        prepend_elements=[_note_el("请确认后再继续。", element_id="nlm_cfm_note")],
        element_id="nlm_confirm",
    )


def build_select_card(
    *,
    title: str,
    markdown: str,
    options: Sequence[Dict[str, Any]],
    action: str,
    kind: str = "",
    session_id: str = "",
    chat_id: str = "",
    placeholder: str = "请选择",
    subtitle: str = "选择一项",
    extra_value: Optional[Dict[str, Any]] = None,
    buttons: Optional[Sequence[Dict[str, Any]]] = None,
    multi: bool = False,
    initial: str = "",
    template: str = TEMPLATE_SETUP,
) -> Dict[str, Any]:
    spec: Dict[str, Any] = {
        "action": action,
        "kind": kind or action,
        "session_id": session_id,
        "chat_id": chat_id,
        "placeholder": placeholder,
        "options": list(options),
        "multi": multi,
        "initial": initial,
    }
    if extra_value:
        spec.update(extra_value)
    return build_interactive_card(
        title=title,
        markdown=markdown,
        subtitle=subtitle,
        template=template,
        icon_token="member-outlined",
        selects=[spec],
        buttons=buttons,
        element_id="nlm_select_c",
    )


def stats_to_visuals(
    stats: Optional[Dict[str, Any]] = None,
    usage: Optional[Dict[str, Any]] = None,
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    """Return (chart_element or None, metric rows). Local data only."""
    blob = dict(stats or {})
    if isinstance(blob.get("result"), dict):
        blob = {**blob, **blob["result"]}
    kind = str(blob.get("kind") or "").strip()
    metrics: List[Dict[str, Any]] = []
    option: Optional[Dict[str, Any]] = None

    if kind == "kb_sync" or any(k in blob for k in ("scanned", "added", "updated", "skipped")):
        added = int(blob.get("added") or 0)
        updated = int(blob.get("updated") or 0)
        skipped = int(blob.get("skipped") or 0)
        scanned = int(blob.get("scanned") or (added + updated + skipped))
        metrics = [
            {"label": "扫描", "value": scanned},
            {"label": "新增", "value": added},
            {"label": "更新", "value": updated},
            {"label": "跳过", "value": skipped},
        ]
        option = {
            "title": {"text": "知识库同步"},
            "xAxis": {"data": ["新增", "更新", "跳过"]},
            "series": [{"type": "bar", "data": [added, updated, skipped]}],
        }
    elif kind == "kb_stats" or ("docs" in blob and "chunks" in blob):
        docs = int(blob.get("docs") or 0)
        chunks = int(blob.get("chunks") or 0)
        embedded = int(blob.get("chunks_with_embedding") or blob.get("embedded") or 0)
        metrics = [
            {"label": "文档", "value": docs},
            {"label": "切片", "value": chunks},
            {"label": "已向量", "value": embedded},
        ]
        option = {
            "title": {"text": "知识库统计"},
            "xAxis": {"data": ["文档", "切片", "已向量"]},
            "series": [{"type": "bar", "data": [docs, chunks, embedded]}],
        }

    if isinstance(usage, dict) and usage:
        prompt = int(usage.get("prompt_tokens") or 0)
        completion = int(usage.get("completion_tokens") or 0)
        total = int(usage.get("total_tokens") or (prompt + completion))
        if total or prompt or completion:
            metrics.extend(
                [
                    {"label": "输入 token", "value": prompt},
                    {"label": "输出 token", "value": completion},
                ]
            )
            if option is None and (prompt or completion):
                option = {
                    "title": {"text": "本轮 token"},
                    "xAxis": {"data": ["输入", "输出"]},
                    "series": [{"type": "bar", "data": [prompt, completion]}],
                }

    chart = _chart_el(to_vchart_spec(option, chart_type="bar")) if option else None
    return chart, metrics[:4]


def build_stats_card(
    *,
    title: str = "统计",
    stats: Optional[Dict[str, Any]] = None,
    usage: Optional[Dict[str, Any]] = None,
    markdown: str = "",
    chart_option: Optional[Dict[str, Any]] = None,
    chart_type: str = "bar",
) -> Dict[str, Any]:
    extras: List[Dict[str, Any]] = []
    chart = _chart_el(to_vchart_spec(chart_option, chart_type=chart_type)) if chart_option else None
    metrics: List[Dict[str, Any]] = []
    if chart is None:
        chart, metrics = stats_to_visuals(stats, usage)
    else:
        _, metrics = stats_to_visuals(stats, usage)
    if chart:
        extras.append(chart)
    cols = _metric_columns(metrics)
    if cols:
        extras.append(cols)
    if not extras and not markdown:
        markdown = "暂无统计数据。"
    return build_interactive_card(
        title=title,
        markdown=markdown,
        subtitle="本地数据",
        template=TEMPLATE_STATS,
        icon_token="member-outlined",
        extra_elements=extras,
        element_id="nlm_stats",
    )


def build_chart_card(
    *,
    title: str = "图表",
    option: Optional[Dict[str, Any]] = None,
    chart_type: str = "bar",
    markdown: str = "",
    metrics: Optional[Sequence[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    spec = to_vchart_spec(option, chart_type=chart_type)
    extras: List[Dict[str, Any]] = []
    chart = _chart_el(spec)
    if chart:
        extras.append(chart)
    else:
        cols = _metric_columns(metrics or [])
        if cols:
            extras.append(cols)
        if not markdown:
            markdown = "当前客户端未展示图表，已改为指标说明。"
    return build_interactive_card(
        title=title,
        markdown=markdown,
        subtitle="图表",
        template=TEMPLATE_STATS,
        icon_token="member-outlined",
        extra_elements=extras,
        element_id="nlm_chart_c",
    )


def build_approval_card(
    *,
    call_id: str,
    name: str,
    base: str = "",
    arguments: Any = None,
) -> Dict[str, Any]:
    tool = (base or name or "tool").strip()
    body = (
        f"**需要批准工具调用**\n\n`{tool}`\n\n"
        f"{_fence(_preview_args(arguments), 'json')}"
    )
    return build_interactive_card(
        title="工具审批",
        markdown=body,
        subtitle="需要确认",
        template=TEMPLATE_APPROVAL,
        icon_token="warning-outlined",
        prepend_elements=[_note_el("请确认后再执行该工具。", element_id="nlm_cfm_note")],
        buttons=[
            {
                "label": "仅允许这次",
                "action": "allow",
                "kind": "approval",
                "call_id": call_id,
                "type": "primary",
            },
            {
                "label": "本会话自动接受",
                "action": "allow_session",
                "kind": "approval",
                "call_id": call_id,
                "type": "default",
            },
            {
                "label": "拒绝",
                "action": "deny",
                "kind": "approval",
                "call_id": call_id,
                "type": "danger",
            },
        ],
        element_id="nlm_approve",
    )


def build_ask_card(
    *,
    call_id: str,
    title: str = "",
    questions: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    qs = list(questions or [])
    lines = [f"**{(title or '需要你的选择').strip()}**", ""]
    buttons: List[Dict[str, Any]] = []
    selects: List[Dict[str, Any]] = []
    for i, q in enumerate(qs[:4]):
        if not isinstance(q, dict):
            continue
        qid = str(q.get("id") or f"q{i+1}")
        prompt = str(q.get("prompt") or q.get("question") or qid)
        lines.append(f"{i + 1}. {prompt}")
        opts = q.get("options") or []
        if not isinstance(opts, list):
            continue
        parsed: List[Dict[str, Any]] = []
        for opt in opts[:MAX_SELECT_OPTIONS]:
            if not isinstance(opt, dict):
                continue
            oid = str(opt.get("id") or opt.get("value") or "")
            label = str(opt.get("label") or oid)[:40]
            if oid:
                parsed.append({"label": label, "value": oid})
        if not parsed:
            continue
        # Official select when options would overflow a 6-button row.
        if len(parsed) > 3 or i > 0:
            selects.append(
                {
                    "action": "submit",
                    "kind": "ask_user",
                    "call_id": call_id,
                    "question_id": qid,
                    "placeholder": truncate(prompt, 20) or "请选择",
                    "options": parsed,
                    "multi": bool(q.get("multi")),
                }
            )
        elif i == 0:
            for opt in parsed[:4]:
                buttons.append(
                    {
                        "label": opt["label"],
                        "action": "submit",
                        "kind": "ask_user",
                        "call_id": call_id,
                        "answers": {qid: opt["value"]},
                        "type": "primary",
                    }
                )
    if not buttons and not selects:
        buttons.append(
            {
                "label": "继续",
                "action": "submit",
                "kind": "ask_user",
                "call_id": call_id,
                "answers": {},
                "type": "primary",
            }
        )
    buttons.append(
        {
            "label": "取消",
            "action": "deny",
            "kind": "ask_user",
            "call_id": call_id,
            "type": "danger",
        }
    )
    return build_interactive_card(
        title="询问用户",
        markdown="\n".join(lines).strip(),
        subtitle="需要你的选择",
        template=TEMPLATE_ASK,
        icon_token="member-outlined",
        buttons=buttons,
        selects=selects,
        element_id="nlm_ask",
    )


def build_plan_review_card(
    *,
    call_id: str,
    title: str = "",
    plan: str = "",
) -> Dict[str, Any]:
    preview = feishu_markdown((plan or "").strip(), limit=1_800)
    heading = (title or "计划审阅").strip()
    body = f"**{heading}**\n\n{preview or '_(empty plan)_'}"
    return build_interactive_card(
        title="计划审阅",
        markdown=body,
        subtitle="请确认后再执行",
        template=TEMPLATE_PLAN,
        icon_token="todo-outlined",
        buttons=[
            {
                "label": "批准并执行",
                "action": "approve",
                "kind": "plan_review",
                "call_id": call_id,
                "type": "primary",
            },
            {
                "label": "继续规划",
                "action": "keep_planning",
                "kind": "plan_review",
                "call_id": call_id,
                "type": "default",
            },
            {
                "label": "稍后自己说",
                "action": "deny",
                "kind": "plan_review",
                "call_id": call_id,
                "type": "danger",
            },
        ],
        element_id="nlm_plan",
    )


def build_gate_resolved_card(title: str, detail: str) -> Dict[str, Any]:
    return build_interactive_card(
        title=title or "已处理",
        markdown=detail or "已处理",
        subtitle="已确认",
        template=TEMPLATE_OK,
        icon_token="yes-outlined",
        prepend_elements=[_note_el("操作已记录。", element_id="nlm_ok_note")],
        element_id="nlm_gate",
    )


def build_provider_pick_card(
    *,
    providers: List[Dict[str, Any]],
    session_id: str,
    chat_id: str,
    page: int = 0,
) -> Dict[str, Any]:
    from src.adapters.feishu.model_pick import page_slice

    chunk, page, has_more = page_slice(providers, page, page_size=MAX_SELECT_OPTIONS)
    lines = [
        "**请先选择本对话使用的 Provider**",
        "",
        "用下拉选择，而不是一排按钮。选定后本会话都会使用该 Provider / 模型。",
        "需要更换时可发送：`切换模型`，或在回复卡「会话设置」里切换。",
        "",
    ]
    options: List[Dict[str, Any]] = []
    if not chunk:
        lines.append("（当前页没有可用 Provider）")
    for p in chunk:
        pid = str(p.get("id") or "")
        label = str(p.get("label") or pid)[:36]
        src = str(p.get("source") or "")
        if src == "custom":
            label = f"{label}·自定义"
        n_models = len(p.get("models") or [])
        lines.append(f"- `{pid}` · {n_models} 个模型")
        if pid:
            options.append({"label": label or pid, "value": pid, "icon_token": "member-outlined"})
    buttons: List[Dict[str, Any]] = []
    if page > 0:
        buttons.append(
            {
                "label": "上一页",
                "action": "page_providers",
                "kind": "provider_pick",
                "session_id": session_id,
                "chat_id": chat_id,
                "page": page - 1,
                "type": "default",
            }
        )
    if has_more:
        buttons.append(
            {
                "label": "下一页",
                "action": "page_providers",
                "kind": "provider_pick",
                "session_id": session_id,
                "chat_id": chat_id,
                "page": page + 1,
                "type": "default",
            }
        )
    selects = []
    if options:
        selects.append(
            {
                "action": "pick_provider",
                "kind": "provider_pick",
                "session_id": session_id,
                "chat_id": chat_id,
                "placeholder": "选择 Provider",
                "options": options,
            }
        )
    return build_interactive_card(
        title="选择 Provider",
        markdown="\n".join(lines).strip(),
        subtitle="开始对话",
        template=TEMPLATE_SETUP,
        icon_token="member-outlined",
        selects=selects,
        buttons=buttons,
        element_id="nlm_prov",
    )


def build_model_pick_card(
    *,
    provider_id: str,
    provider_label: str,
    models: List[str],
    session_id: str,
    chat_id: str,
    page: int = 0,
) -> Dict[str, Any]:
    from src.adapters.feishu.model_pick import page_slice

    chunk, page, has_more = page_slice(models, page, page_size=MAX_SELECT_OPTIONS)
    title_label = (provider_label or provider_id or "").strip()
    lines = [
        f"**选择模型** · `{title_label}`",
        "",
        "从下拉列表点选后即绑定到本对话，并继续处理你刚才的消息。",
        "",
    ]
    options = [{"label": str(name)[:40], "value": str(name)} for name in chunk if str(name).strip()]
    buttons: List[Dict[str, Any]] = [
        {
            "label": "返回 Provider",
            "action": "back_providers",
            "kind": "provider_pick",
            "session_id": session_id,
            "chat_id": chat_id,
            "page": 0,
            "type": "default",
        }
    ]
    if page > 0:
        buttons.append(
            {
                "label": "上一页",
                "action": "page_models",
                "kind": "model_pick",
                "provider_id": provider_id,
                "session_id": session_id,
                "chat_id": chat_id,
                "page": page - 1,
                "type": "default",
            }
        )
    if has_more:
        buttons.append(
            {
                "label": "下一页",
                "action": "page_models",
                "kind": "model_pick",
                "provider_id": provider_id,
                "session_id": session_id,
                "chat_id": chat_id,
                "page": page + 1,
                "type": "default",
            }
        )
    selects = []
    if options:
        selects.append(
            {
                "action": "pick_model",
                "kind": "model_pick",
                "provider_id": provider_id,
                "session_id": session_id,
                "chat_id": chat_id,
                "placeholder": "选择模型",
                "options": options,
            }
        )
    return build_interactive_card(
        title="选择模型",
        markdown="\n".join(lines).strip(),
        subtitle=title_label or "模型",
        template=TEMPLATE_SETUP,
        icon_token="member-outlined",
        selects=selects,
        buttons=buttons,
        element_id="nlm_model",
    )


def build_no_provider_card() -> Dict[str, Any]:
    return build_interactive_card(
        title="未配置 Provider",
        markdown=(
            "当前没有可用的模型 Provider。\n\n"
            "请先打开 Web **设置 → 模型 Provider**：\n"
            "1. 配置内置供应商的 API Key，或新增自定义 Provider\n"
            "2. 测通后点「设为默认」\n"
            "3. 回到飞书再发一条消息，即可从卡片中选择 Provider / 模型"
        ),
        subtitle="需要配置",
        template=TEMPLATE_WARN,
        icon_token="warning-outlined",
        element_id="nlm_noprov",
    )


def build_session_cleared_card() -> Dict[str, Any]:
    return build_interactive_card(
        title="会话已清空",
        markdown="本对话上下文已删除。发送下一条消息将重新选择 Provider / 模型。",
        subtitle="已完成",
        template=TEMPLATE_OK,
        icon_token="yes-outlined",
        element_id="nlm_clear",
    )


def default_reply_buttons(
    *,
    session_id: str,
    chat_id: str,
    retry_text: str = "",
) -> List[Dict[str, Any]]:
    return [
        {
            "label": "再问一次",
            "action": "retry",
            "kind": "conversation",
            "payload": truncate(retry_text, 400),
            "session_id": session_id,
            "chat_id": chat_id,
            "type": "primary",
        },
        {
            "label": "清空会话",
            "action": "clear",
            "kind": "conversation",
            "payload": session_id,
            "session_id": session_id,
            "chat_id": chat_id,
            "type": "danger",
            "confirm": {
                "title": "清空会话",
                "text": "将删除本对话上下文，下次发言需重新选择模型。",
            },
        },
    ]


def default_reply_selects(
    *,
    session_id: str,
    chat_id: str,
) -> List[Dict[str, Any]]:
    """Model / KB / preset overflow — official select instead of a 6-button row."""
    return [
        {
            "action": "session_setting",
            "kind": "conversation",
            "session_id": session_id,
            "chat_id": chat_id,
            "placeholder": "会话设置",
            "options": [
                {"label": "切换模型", "value": "back_providers", "icon_token": "member-outlined"},
                {"label": "权限预设", "value": "open_preset", "icon_token": "todo-outlined"},
                {"label": "使用本地知识库", "value": "kb:local", "icon_token": "file-outlined"},
            ],
        }
    ]


def build_preset_pick_card(*, session_id: str, chat_id: str) -> Dict[str, Any]:
    from src.common.permission_presets import PRESETS

    options = [
        {"label": f"{cfg['label']} · {cfg['hint']}"[:40], "value": cfg["id"]}
        for cfg in PRESETS.values()
    ]
    return build_select_card(
        title="权限预设",
        markdown="选择本对话的权限预设。只读会禁止写文件与 shell；全权限不再询问。",
        options=options,
        action="pick_preset",
        kind="preset_pick",
        session_id=session_id,
        chat_id=chat_id,
        placeholder="选择预设",
        subtitle="会话设置",
    )


def build_kb_pick_card(
    *,
    session_id: str,
    chat_id: str,
    current_kb: str = "",
) -> Dict[str, Any]:
    options = [{"label": "本地知识库", "value": "local"}]
    current = (current_kb or "").strip()
    if current and current != "local":
        options.append({"label": truncate(f"当前绑定 · {current}", 40), "value": current})
    note = "飞书侧不拉取远程 WeKnora 列表。可切回本地知识库；远程 KB 请在 Web 绑定。"
    return build_select_card(
        title="绑定知识库",
        markdown=note,
        options=options,
        action="pick_kb",
        kind="kb_pick",
        session_id=session_id,
        chat_id=chat_id,
        placeholder="选择知识库",
        subtitle="本地优先",
        initial="local",
    )


def extract_stats_payload(payload: Any) -> Optional[Dict[str, Any]]:
    """Pull kb_stats / kb_sync_docs numbers from a tool_result (local data)."""
    if not isinstance(payload, dict):
        return None
    name = str(payload.get("name") or payload.get("base") or "")
    blobs: List[Any] = [payload, payload.get("result")]
    result = payload.get("result")
    if isinstance(result, dict) and isinstance(result.get("result"), dict):
        blobs.append(result["result"])
    for blob in blobs:
        if not isinstance(blob, dict):
            continue
        if (name == "kb_stats" or "docs" in blob) and "chunks" in blob:
            return {
                "kind": "kb_stats",
                "docs": int(blob.get("docs") or 0),
                "chunks": int(blob.get("chunks") or 0),
                "chunks_with_embedding": int(blob.get("chunks_with_embedding") or blob.get("embedded") or 0),
                "hybrid_ready": bool(blob.get("hybrid_ready")),
            }
        if name in {"kb_sync_docs", "kb_sync_feishu"} or "scanned" in blob:
            if "scanned" not in blob and "added" not in blob:
                continue
            return {
                "kind": "kb_sync",
                "scanned": int(blob.get("scanned") or 0),
                "added": int(blob.get("added") or 0),
                "updated": int(blob.get("updated") or 0),
                "skipped": int(blob.get("skipped") or 0),
            }
    return None


def extract_citations(tool_result: Any) -> str:
    """Pull citations_md / hit list out of a tool_result payload."""
    if not isinstance(tool_result, dict):
        return ""
    result = tool_result.get("result")
    blobs: List[Any] = [tool_result, result]
    if isinstance(result, dict) and isinstance(result.get("result"), dict):
        blobs.append(result["result"])
    for blob in blobs:
        if not isinstance(blob, dict):
            continue
        cite = blob.get("citations_md")
        if isinstance(cite, str) and cite.strip():
            return truncate(cite.strip(), CITATION_MAX_CHARS)
    hits: Optional[Iterable[Any]] = None
    for blob in blobs:
        if isinstance(blob, dict):
            for key in ("results", "hits", "documents"):
                if isinstance(blob.get(key), list):
                    hits = blob[key]
                    break
        if hits is not None:
            break
    if not hits:
        return ""
    lines: List[str] = []
    for row in list(hits)[:6]:
        if not isinstance(row, dict):
            continue
        cite = str(row.get("citation") or row.get("title") or row.get("path") or "").strip()
        if cite:
            lines.append(f"- {truncate(cite, 160)}")
    return "\n".join(lines)


def summarize_tool_result(payload: Dict[str, Any]) -> Tuple[str, str]:
    """Return (status, short summary) for the streaming tool list."""
    ok = bool(payload.get("success"))
    err = str(payload.get("error") or "").strip()
    if err and not ok:
        return "error", truncate(sanitize_error(err, limit=80), 80)
    result = payload.get("result")
    name = str(payload.get("name") or payload.get("base") or "")
    if isinstance(result, dict):
        cite = extract_citations(payload)
        if cite:
            hits = result.get("results") or result.get("hits") or []
            n = len(hits) if isinstance(hits, list) else 0
            return "ok", f"{n} 条命中" if n else "已引用"
        if name.endswith("search") or "search" in name:
            hits = result.get("results") or result.get("hits") or []
            if isinstance(hits, list):
                return "ok", f"{len(hits)} 条命中"
        if result.get("path") or result.get("file"):
            return "ok", truncate(str(result.get("path") or result.get("file")), 60)
    if result is None:
        return ("ok" if ok else "error"), ""
    return "ok" if ok else "error", ""


# Channel card catalog — builders used by the Feishu adapter.
CARD_CATALOG = {
    CARD_TYPE_THINKING: build_thinking_card,
    CARD_TYPE_ANSWER: build_reply_card,
    CARD_TYPE_SELECT: build_select_card,
    CARD_TYPE_STATS: build_stats_card,
    CARD_TYPE_CHART: build_chart_card,
    CARD_TYPE_ERROR: build_error_card,
    CARD_TYPE_CONFIRM: build_confirm_card,
}
