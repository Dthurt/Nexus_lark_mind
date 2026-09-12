"""Feishu interactive / streaming card builders."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional


def build_text_card(title: str, content: str, *, buttons: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    elements: List[Dict[str, Any]] = [
        {
            "tag": "div",
            "text": {"tag": "lark_md", "content": content or "…"},
        }
    ]
    if buttons:
        actions = []
        for btn in buttons:
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
            actions.append(
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": btn.get("label", "OK")},
                    "type": btn.get("type") or "primary",
                    "value": value,
                }
            )
        elements.append({"tag": "action", "actions": actions})

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": title},
            "template": "blue",
        },
        "elements": elements,
    }


def build_streaming_card(title: str, content: str) -> Dict[str, Any]:
    return build_text_card(title, content + (" ▌" if content else "思考中…"))


def _preview_args(arguments: Any, limit: int = 600) -> str:
    try:
        text = json.dumps(arguments or {}, ensure_ascii=False, indent=2)
    except Exception:
        text = str(arguments or "")
    if len(text) > limit:
        return text[: limit - 20] + "\n…"
    return text


def build_approval_card(
    *,
    call_id: str,
    name: str,
    base: str = "",
    arguments: Any = None,
) -> Dict[str, Any]:
    """Interactive Allow / Deny card aligned with Web ApprovalDock."""
    tool = (base or name or "tool").strip()
    body = f"**需要批准工具调用**\n\n`{tool}`\n\n```json\n{_preview_args(arguments)}\n```"
    return build_text_card(
        "工具审批",
        body,
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
    )


def build_ask_card(
    *,
    call_id: str,
    title: str = "",
    questions: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Interactive ask_user card — option buttons for the first question + dismiss."""
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
    return build_text_card("询问用户", "\n".join(lines).strip(), buttons=buttons)


def build_plan_review_card(
    *,
    call_id: str,
    title: str = "",
    plan: str = "",
) -> Dict[str, Any]:
    """Interactive plan review card — approve / keep planning / dismiss."""
    preview = (plan or "").strip()
    if len(preview) > 1800:
        preview = preview[:1780] + "\n…"
    body = f"**{(title or '计划审阅').strip()}**\n\n{preview or '_(empty plan)_'}"
    return build_text_card(
        "计划审阅",
        body,
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
    )


def build_gate_resolved_card(title: str, detail: str) -> Dict[str, Any]:
    return build_text_card(title, detail)


def build_provider_pick_card(
    *,
    providers: List[Dict[str, Any]],
    session_id: str,
    chat_id: str,
    page: int = 0,
) -> Dict[str, Any]:
    """Required first-step: pick a configured provider for this Feishu conversation."""
    from src.adapters.feishu.model_pick import page_slice

    chunk, page, has_more = page_slice(providers, page, page_size=5)
    lines = [
        "**请先选择本对话使用的 Provider**",
        "",
        "选定后，本会话后续消息都会使用该 Provider / 模型。",
        "需要更换时可发送：`切换模型`",
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
    return build_text_card("选择 Provider", "\n".join(lines).strip(), buttons=buttons)


def build_model_pick_card(
    *,
    provider_id: str,
    provider_label: str,
    models: List[str],
    session_id: str,
    chat_id: str,
    page: int = 0,
) -> Dict[str, Any]:
    """Second-step: pick a model under the chosen provider."""
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
    return build_text_card("选择模型", "\n".join(lines).strip(), buttons=buttons)


def build_no_provider_card() -> Dict[str, Any]:
    return build_text_card(
        "未配置 Provider",
        "当前没有可用的模型 Provider。\n\n"
        "请先打开 Web **设置 → 模型 Provider**：\n"
        "1. 配置内置供应商的 API Key，或新增自定义 Provider\n"
        "2. 测通后点「设为默认」\n"
        "3. 回到飞书再发一条消息，即可从卡片中选择 Provider / 模型",
    )

