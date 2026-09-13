"""DingTalk inbound event parsing (robot HTTP / encrypted callback)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple
from xml.etree import ElementTree as ET

from src.adapters import im_crypto

logger = logging.getLogger(__name__)


@dataclass
class DingTalkMessage:
    text: str
    user_id: str
    conversation_id: str
    conversation_type: str
    session_webhook: str
    message_id: str
    raw: Dict[str, Any]


def classify_payload(payload: Dict[str, Any]) -> Tuple[str, Any]:
    """Return (kind, data). kinds: url_verification | message | ignore."""
    # Encrypted DingTalk enterprise callback often wraps encrypt string.
    if "encrypt" in payload and len(payload) <= 3 and "text" not in payload:
        return "encrypted", payload.get("encrypt") or ""
    # URL verification style (some DingTalk apps echo random)
    if payload.get("type") == "url_verification" or payload.get("EventType") == "check_url":
        return "url_verification", payload
    msg = parse_robot_message(payload)
    if msg and msg.text.strip():
        return "message", msg
    return "ignore", payload


def parse_robot_message(payload: Dict[str, Any]) -> Optional[DingTalkMessage]:
    text_obj = payload.get("text") or {}
    content = ""
    if isinstance(text_obj, dict):
        content = str(text_obj.get("content") or "")
    elif isinstance(text_obj, str):
        content = text_obj
    if not content:
        content = str(payload.get("content") or payload.get("msgContent") or "")
    # Strip @bot mention prefix often present in groups
    content = content.strip()
    user_id = str(
        payload.get("senderStaffId")
        or payload.get("senderId")
        or payload.get("userid")
        or payload.get("SenderId")
        or ""
    )
    conversation_id = str(
        payload.get("conversationId")
        or payload.get("chatId")
        or payload.get("ConversationId")
        or ""
    )
    conversation_type = str(payload.get("conversationType") or payload.get("chatType") or "")
    session_webhook = str(payload.get("sessionWebhook") or payload.get("SessionWebhook") or "")
    message_id = str(payload.get("msgId") or payload.get("messageId") or payload.get("MsgId") or "")
    if not content and not session_webhook:
        return None
    return DingTalkMessage(
        text=content,
        user_id=user_id or "unknown",
        conversation_id=conversation_id or user_id or "dm",
        conversation_type=conversation_type,
        session_webhook=session_webhook,
        message_id=message_id,
        raw=payload,
    )


def decrypt_if_needed(
    payload: Dict[str, Any],
    *,
    encoding_aes_key: str,
    receive_id: str,
) -> Dict[str, Any]:
    encrypt = payload.get("encrypt")
    if not encrypt or not encoding_aes_key:
        return payload
    plain = im_crypto.decrypt_payload(
        encoding_aes_key=encoding_aes_key,
        receive_id=receive_id,
        encrypt_b64=str(encrypt),
    )
    # May be JSON or XML
    plain = plain.strip()
    if plain.startswith("{"):
        try:
            return json.loads(plain)
        except json.JSONDecodeError:
            pass
    if plain.startswith("<"):
        return _xml_to_dict(plain)
    return {"text": {"content": plain}, "raw_plain": plain}


def _xml_to_dict(xml_text: str) -> Dict[str, Any]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return {"text": {"content": xml_text}}
    out: Dict[str, Any] = {}
    for child in root:
        out[child.tag] = (child.text or "").strip()
    content = out.get("Content") or out.get("content") or ""
    return {
        "text": {"content": content},
        "senderStaffId": out.get("FromUserName") or out.get("UserId") or "",
        "conversationId": out.get("ChatId") or out.get("ConversationId") or "",
        "msgId": out.get("MsgId") or "",
        "xml": out,
    }
