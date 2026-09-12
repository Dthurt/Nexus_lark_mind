"""Feishu interactive / streaming card builders."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional


def build_text_card(title: str, content: str, *, buttons: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
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


def build_gate_resolved_card(title: str, detail: str) -> Dict[str, Any]:
    return build_text_card(title, detail)
