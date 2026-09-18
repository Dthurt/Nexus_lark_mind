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
MAX_TOOL_ROWS = 6
MAX_BUTTONS = 6
MAX_BUTTON_LABEL = 40

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


def _fit_card(card: Dict[str, Any]) -> Dict[str, Any]:
    raw = json.dumps(card, ensure_ascii=False)
    if len(raw.encode("utf-8")) <= CARD_JSON_MAX_BYTES:
        return card
    body = card.get("body") or {}
    elements = list(body.get("elements") or [])
    for el in elements:
        if isinstance(el, dict) and el.get("tag") == "markdown":
            el["content"] = truncate(str(el.get("content") or ""), 4_000)
            break
    body["elements"] = elements[:12]
    card["body"] = body
    raw = json.dumps(card, ensure_ascii=False)
    if len(raw.encode("utf-8")) > CARD_JSON_MAX_BYTES:
        for el in elements:
            if isinstance(el, dict) and el.get("tag") == "markdown":
                el["content"] = truncate(str(el.get("content") or ""), 1_800)
        body["elements"] = elements[:8]
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
    streaming: bool = False,
    element_id: str = "nlm_body",
) -> Dict[str, Any]:
    """Canonical Card JSON 2.0 builder."""
    elements: List[Dict[str, Any]] = []
    body_md = feishu_markdown(markdown) if markdown else ""
    if body_md:
        elements.append(_markdown_el(body_md, element_id=element_id or "nlm_body"))
    for extra in extra_elements or []:
        if extra:
            elements.append(dict(extra))
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
        if tag == "button":
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
    lines = ["**工具进度**"]
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


def build_streaming_card(
    title: str,
    content: str,
    *,
    status: str = "",
    tools: Optional[Sequence[Dict[str, Any]]] = None,
    user_preview: str = "",
    citations: str = "",
) -> Dict[str, Any]:
    extras: List[Dict[str, Any]] = []
    notes: List[str] = []
    preview = truncate((user_preview or "").strip(), 80)
    if preview:
        notes.append(f"正在回复：**{preview}**")
    status_text = (status or "").strip()
    if status_text:
        notes.append(status_text)
    elif not (content or "").strip() and not tools:
        notes.append("生成中…")
    if notes:
        extras.append(
            _markdown_el(
                "<note icon='true'>" + "<br/>".join(notes) + "</note>",
                element_id="nlm_note",
            )
        )
    tool_md = _tool_markdown(tools or [])
    if tool_md:
        extras.append(_hr())
        extras.append(_markdown_el(tool_md, element_id="nlm_tools", icon_token="todo-outlined"))
    cite = truncate((citations or "").strip(), CITATION_MAX_CHARS)
    if cite:
        extras.append(_hr())
        extras.append(
            _markdown_el(
                "**引用来源**\n\n" + cite,
                element_id="nlm_cites",
                icon_token="file-outlined",
            )
        )
    body = feishu_markdown(content)
    if body:
        body = body + " ▌"
    elif not extras:
        body = "生成中… ▌"
    return build_interactive_card(
        title=title or "Nexus Lark Mind",
        markdown=body,
        subtitle="生成中",
        template=TEMPLATE_STREAM,
        icon_token="chat-outlined",
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
    user_preview: str = "",
) -> Dict[str, Any]:
    extras: List[Dict[str, Any]] = []
    tool_md = _tool_markdown(tools or [])
    if tool_md:
        extras.append(_hr())
        extras.append(_markdown_el(tool_md, element_id="nlm_tools", icon_token="todo-outlined"))
    cite = truncate((citations or "").strip(), CITATION_MAX_CHARS)
    if cite:
        extras.append(_hr())
        extras.append(
            _markdown_el(
                "**引用来源**\n\n" + cite,
                element_id="nlm_cites",
                icon_token="file-outlined",
            )
        )
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
        body = f"**模型暂时限流**\n\n{detail}\n\n稍后再试，或点重试。"
        template = TEMPLATE_WARN
        subtitle = "限流"
        icon = "warning-outlined"
    else:
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
        streaming=False,
        element_id="nlm_error",
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
    for i, q in enumerate(qs[:4]):
        if not isinstance(q, dict):
            continue
        qid = str(q.get("id") or f"q{i+1}")
        prompt = str(q.get("prompt") or q.get("question") or qid)
        lines.append(f"{i + 1}. {prompt}")
        opts = q.get("options") or []
        if isinstance(opts, list) and i == 0:
            for opt in opts[:4]:
                if not isinstance(opt, dict):
                    continue
                oid = str(opt.get("id") or opt.get("value") or "")
                label = str(opt.get("label") or oid)[:40]
                if not oid:
                    continue
                buttons.append(
                    {
                        "label": label,
                        "action": "submit",
                        "kind": "ask_user",
                        "call_id": call_id,
                        "answers": {qid: oid},
                        "type": "primary",
                    }
                )
    if not buttons:
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
        subtitle="已完成",
        template=TEMPLATE_OK,
        icon_token="yes-outlined",
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

    chunk, page, has_more = page_slice(providers, page, page_size=5)
    lines = [
        "**请先选择本对话使用的 Provider**",
        "",
        "选定后，本会话后续消息都会使用该 Provider / 模型。",
        "需要更换时可发送：`切换模型`，或点回复卡片上的「切换模型」。",
        "",
    ]
    if not chunk:
        lines.append("（当前页没有可用 Provider）")
    buttons: List[Dict[str, Any]] = []
    for p in chunk:
        pid = str(p.get("id") or "")
        label = str(p.get("label") or pid)[:36]
        src = str(p.get("source") or "")
        if src == "custom":
            label = f"{label}·自定义"
        lines.append(f"- `{pid}` · {len(p.get('models') or [])} 个模型")
        buttons.append(
            {
                "label": label or pid,
                "action": "pick_provider",
                "kind": "provider_pick",
                "provider_id": pid,
                "session_id": session_id,
                "chat_id": chat_id,
                "type": "primary",
            }
        )
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
    return build_interactive_card(
        title="选择 Provider",
        markdown="\n".join(lines).strip(),
        subtitle="开始对话",
        template=TEMPLATE_SETUP,
        icon_token="member-outlined",
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

    chunk, page, has_more = page_slice(models, page, page_size=5)
    title_label = (provider_label or provider_id or "").strip()
    lines = [
        f"**选择模型** · `{title_label}`",
        "",
        "点选后即绑定到本对话，并继续处理你刚才的消息。",
        "",
    ]
    buttons: List[Dict[str, Any]] = []
    for name in chunk:
        buttons.append(
            {
                "label": str(name)[:40],
                "action": "pick_model",
                "kind": "model_pick",
                "provider_id": provider_id,
                "model_name": name,
                "session_id": session_id,
                "chat_id": chat_id,
                "type": "primary",
            }
        )
    buttons.append(
        {
            "label": "返回 Provider",
            "action": "back_providers",
            "kind": "provider_pick",
            "session_id": session_id,
            "chat_id": chat_id,
            "page": 0,
            "type": "default",
        }
    )
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
    return build_interactive_card(
        title="选择模型",
        markdown="\n".join(lines).strip(),
        subtitle=title_label or "模型",
        template=TEMPLATE_SETUP,
        icon_token="member-outlined",
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
            "label": "切换模型",
            "action": "back_providers",
            "kind": "provider_pick",
            "session_id": session_id,
            "chat_id": chat_id,
            "page": 0,
            "type": "default",
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
