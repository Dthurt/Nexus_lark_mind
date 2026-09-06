"""Feishu event parsing — messages, card actions, url verification."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional, Tuple

from pydantic import BaseModel, Field


class ParsedFeishuMessage(BaseModel):
    message_id: str
    chat_id: str
    user_id: str
    text: str
    message_type: str = "text"
    raw: Dict[str, Any] = Field(default_factory=dict)


class ParsedCardAction(BaseModel):
    user_id: str
    open_message_id: str
    action: str
    payload: str = ""
    raw: Dict[str, Any] = Field(default_factory=dict)


def parse_url_verification(payload: Dict[str, Any]) -> Optional[str]:
    if payload.get("type") == "url_verification":
        return payload.get("challenge")
    header = payload.get("header") or {}
    if header.get("event_type") == "url_verification":
        return payload.get("challenge")
    return None


def extract_event_body(payload: Dict[str, Any]) -> Dict[str, Any]:
    # v2 schema nests under event
    if "event" in payload:
        return payload["event"]
    return payload


def parse_im_message(payload: Dict[str, Any]) -> Optional[ParsedFeishuMessage]:
    header = payload.get("header") or {}
    event_type = header.get("event_type") or payload.get("type")
    if event_type not in {"im.message.receive_v1", "im.message.receive_v1.0", "message"}:
        # also accept older schema
        if "event" not in payload and payload.get("type") != "event_callback":
            if event_type and "message" not in str(event_type):
                return None

    event = extract_event_body(payload)
    message = event.get("message") or {}
    sender = event.get("sender") or {}
    msg_type = message.get("message_type") or message.get("msg_type") or "text"
    content_raw = message.get("content") or "{}"
    try:
        content = json.loads(content_raw) if isinstance(content_raw, str) else content_raw
    except json.JSONDecodeError:
        content = {"text": str(content_raw)}

    text = content.get("text") or content.get("content") or ""
    if not text and msg_type != "text":
        text = f"[{msg_type} message]"

    user_id = (
        (sender.get("sender_id") or {}).get("open_id")
        or sender.get("open_id")
        or sender.get("user_id")
        or "unknown"
    )
    message_id = message.get("message_id") or message.get("msg_id") or ""
    chat_id = message.get("chat_id") or ""
    if not message_id:
        return None
    return ParsedFeishuMessage(
        message_id=message_id,
        chat_id=chat_id,
        user_id=user_id,
        text=text.strip(),
        message_type=msg_type,
        raw=payload,
    )


def parse_card_action(payload: Dict[str, Any]) -> Optional[ParsedCardAction]:
    header = payload.get("header") or {}
    event_type = header.get("event_type") or payload.get("type")
    if event_type not in {"card.action.trigger", "interactive"} and "action" not in payload:
        # interactive callback often comes as top-level
        if "open_message_id" not in payload and "action" not in payload:
            return None

    action_obj = payload.get("action") or (payload.get("event") or {}).get("action") or {}
    value = action_obj.get("value") or {}
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            value = {"action": value}

    user = payload.get("operator") or payload.get("user_id") or {}
    if isinstance(user, dict):
        user_id = user.get("open_id") or user.get("user_id") or "unknown"
    else:
        user_id = str(user)

    return ParsedCardAction(
        user_id=user_id,
        open_message_id=payload.get("open_message_id") or "",
        action=str(value.get("action") or "noop"),
        payload=str(value.get("payload") or ""),
        raw=payload,
    )


def classify_payload(payload: Dict[str, Any]) -> Tuple[str, Any]:
    challenge = parse_url_verification(payload)
    if challenge is not None:
        return "url_verification", challenge
    card = parse_card_action(payload)
    if card is not None and (card.action != "noop" or "action" in payload):
        # Prefer message if both somehow match
        msg = parse_im_message(payload)
        if msg is not None and payload.get("header", {}).get("event_type", "").startswith("im.message"):
            return "message", msg
        if "action" in payload or payload.get("header", {}).get("event_type") == "card.action.trigger":
            return "card_action", card
    msg = parse_im_message(payload)
    if msg is not None:
        return "message", msg
    if card is not None:
        return "card_action", card
    return "unknown", payload
