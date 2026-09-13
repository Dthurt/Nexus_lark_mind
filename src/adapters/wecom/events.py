"""WeCom inbound XML / encrypted callback parsing."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple
from xml.etree import ElementTree as ET

from src.adapters import im_crypto

logger = logging.getLogger(__name__)


@dataclass
class WeComMessage:
    text: str
    user_id: str
    agent_id: str
    msg_id: str
    msg_type: str
    raw: Dict[str, str]


def parse_xml(xml_text: str) -> Dict[str, str]:
    root = ET.fromstring(xml_text)
    out: Dict[str, str] = {}
    for child in root:
        out[child.tag] = (child.text or "").strip()
    return out


def classify_xml(fields: Dict[str, str]) -> Tuple[str, Any]:
    msg_type = (fields.get("MsgType") or "").lower()
    if msg_type == "event":
        return "event", fields
    if msg_type == "text":
        msg = WeComMessage(
            text=fields.get("Content") or "",
            user_id=fields.get("FromUserName") or "",
            agent_id=fields.get("AgentID") or fields.get("AgentId") or "",
            msg_id=fields.get("MsgId") or "",
            msg_type=msg_type,
            raw=fields,
        )
        return "message", msg
    return "ignore", fields


def decrypt_post_body(
    *,
    encoding_aes_key: str,
    corp_id: str,
    encrypt_b64: str,
) -> str:
    return im_crypto.decrypt_payload(
        encoding_aes_key=encoding_aes_key,
        receive_id=corp_id,
        encrypt_b64=encrypt_b64,
    )


def extract_encrypt_from_xml(xml_text: str) -> str:
    fields = parse_xml(xml_text)
    return fields.get("Encrypt") or ""


def build_plain_ack() -> str:
    return "success"
