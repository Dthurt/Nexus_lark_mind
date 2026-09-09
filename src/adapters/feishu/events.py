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
    chat_type: str = ""  # p2p | group | ...
    mentions: list = Field(default_factory=list)
    mentioned_bot: bool = False
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


def _mentions_include_bot(mentions: list) -> bool:
    for m in mentions or []:
        if not isinstance(m, dict):
            continue
        mtype = str(m.get("id", {}).get("id_type") or m.get("id_type") or "").lower()
        mentioned_type = str(m.get("mentioned_type") or "").lower()
        name = str(m.get("name") or "").lower()
        if mentioned_type == "bot":
            return True
        if mtype == "open_id" and mentioned_type in {"bot", "app"}:
            return True
        # Some payloads only mark bots via name/key patterns
        if "bot" in mentioned_type or mentioned_type == "app":
            return True
        key = str(m.get("key") or "")
        if key.startswith("@_user_") and mentioned_type == "bot":
            return True
        # Feishu docs: mentioned_type is "user" or "bot"
        if m.get("mentioned_type") == "bot":
            return True
    return False


def strip_mention_placeholders(text: str) -> str:
    import re

    cleaned = re.sub(r"@_user_\d+", " ", text or "")
    cleaned = re.sub(r"<at\s+[^>]+>|</at>", " ", cleaned, flags=re.I)
    return " ".join(cleaned.split()).strip()


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
    chat_type = str(message.get("chat_type") or "").lower()
    mentions = message.get("mentions") or []
    if not isinstance(mentions, list):
        mentions = []
    mentioned_bot = _mentions_include_bot(mentions)
    # Fallback: text still has @_user_ placeholders while mentions array present
    if not mentioned_bot and mentions and "@_user_" in (text or ""):
        # If Feishu delivered this under group_at scope, treat any mention as targeting us
        # when any mention is typed bot; otherwise require explicit bot type.
        mentioned_bot = any(
            isinstance(m, dict) and str(m.get("mentioned_type") or "").lower() == "bot"
            for m in mentions
        )

    if not message_id:
        return None
    return ParsedFeishuMessage(
        message_id=message_id,
        chat_id=chat_id,
        user_id=user_id,
        text=text.strip(),
        message_type=msg_type,
        chat_type=chat_type,
        mentions=mentions,
        mentioned_bot=mentioned_bot,
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
