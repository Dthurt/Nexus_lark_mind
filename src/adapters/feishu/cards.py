"""Feishu interactive / streaming card builders."""

from __future__ import annotations

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
            actions.append(
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": btn.get("label", "OK")},
                    "type": "primary",
                    "value": {"action": btn.get("action", "noop"), "payload": btn.get("payload", "")},
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
