"""Persisted chat-turn errors (stream HTTP 400, model failure, cancel)."""

from __future__ import annotations

from typing import Any, Dict, Optional

from src.common.schemas import ChatMessage, ChatRole

ERROR_KIND = "error"


def format_error_display(error: str, *, cancelled: bool = False) -> str:
    """Same text the workbench shows live for a failed / stopped turn."""
    if cancelled:
        return "已停止生成。"
    text = (error or "unknown").strip() or "unknown"
    if "限流" in text or "429" in text:
        return f"⚠️ {text}"
    return f"错误：{text}"


def is_persisted_error(message: Dict[str, Any] | None) -> bool:
    if not isinstance(message, dict):
        return False
    meta = message.get("metadata") or {}
    if not isinstance(meta, dict):
        return False
    return meta.get("kind") == ERROR_KIND


def build_error_message(
    error: str,
    *,
    cancelled: bool = False,
    task_id: str = "",
    partial: Optional[str] = None,
) -> ChatMessage:
    raw = (error or "unknown").strip() or "unknown"
    meta: Dict[str, Any] = {
        "kind": ERROR_KIND,
        "error": raw,
        "cancelled": bool(cancelled),
    }
    if task_id:
        meta["task_id"] = task_id
    if partial:
        meta["partial"] = partial
    return ChatMessage(
        role=ChatRole.ASSISTANT,
        content=format_error_display(raw, cancelled=cancelled),
        metadata=meta,
    )


def model_history_messages(messages: list) -> list:
    """Drop persisted errors so the next model turn is not polluted."""
    out = []
    for m in messages or []:
        if is_persisted_error(m):
            continue
        out.append(m)
    return out
