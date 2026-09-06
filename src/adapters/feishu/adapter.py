"""Feishu adapter — normalize events, stream card updates via event bus."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

from src.adapters.base_adapter import BaseAdapter
from src.adapters.feishu.cards import build_streaming_card, build_text_card
from src.adapters.feishu.client import FeishuClient
from src.adapters.feishu.crypto import AESCipher, verify_request_signature, verify_token
from src.adapters.feishu.events import classify_payload
from src.common.config import Settings, get_settings
from src.common.rpc_client import RpcClient
from src.common.schemas import BusEvent, ChannelType, EventType, StandardTask
from src.infrastructure.redis_client import RedisClient

logger = logging.getLogger(__name__)


class FeishuAdapter(BaseAdapter):
    channel = ChannelType.FEISHU

    def __init__(
        self,
        orchestrator: RpcClient,
        redis_client: RedisClient,
        settings: Optional[Settings] = None,
    ) -> None:
        super().__init__(orchestrator, redis_client)
        self.settings = settings or get_settings()
        self.client = FeishuClient(self.settings)
        self._card_messages: Dict[str, str] = {}  # task_id -> feishu message_id
        self._buffers: Dict[str, str] = {}
        self._lock = asyncio.Lock()

    async def handle_inbound(self, payload: Dict[str, Any]) -> Optional[StandardTask]:
        kind, data = classify_payload(payload)
        if kind == "url_verification":
            return None
        # Ignore bot/app echoes to avoid loops
        event = payload.get("event") or {}
        sender = event.get("sender") or {}
        if sender.get("sender_type") == "app":
            logger.debug("Ignore feishu app/bot echo message")
            return None
        if kind == "card_action":
            action = data.action
            text = f"[card_action:{action}] {data.payload}".strip()
            task = StandardTask(
                session_id=f"feishu:{data.user_id}",
                channel=ChannelType.FEISHU,
                user_id=data.user_id,
                content=text,
                metadata={
                    "feishu_open_message_id": data.open_message_id,
                    "card_action": action,
                },
            )
            await self.submit(task)
            return task
        if kind == "message":
            msg = data
            task = StandardTask(
                session_id=f"feishu:{msg.chat_id}:{msg.user_id}",
                channel=ChannelType.FEISHU,
                user_id=msg.user_id,
                content=msg.text,
                metadata={
                    "feishu_message_id": msg.message_id,
                    "feishu_chat_id": msg.chat_id,
                },
            )
            # Seed streaming card
            if msg.chat_id:
                card = build_streaming_card("Nexus-Lark-Mind", "")
                sent = await self.client.send_card_to_chat(msg.chat_id, card)
                message_id = (
                    ((sent.get("data") or {}).get("message_id"))
                    if isinstance(sent, dict)
                    else None
                )
                if message_id:
                    self._card_messages[task.task_id] = message_id
            await self.submit(task)
            return task
        logger.debug("Ignored feishu payload kind=%s", kind)
        return None

    def decode_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if "encrypt" in payload and self.settings.feishu_encrypt_key:
            return AESCipher(self.settings.feishu_encrypt_key).decrypt(payload["encrypt"])
        return payload

    def verify(self, payload: Dict[str, Any], *, headers: Dict[str, str], body: str) -> None:
        verify_token(payload, self.settings.feishu_verification_token)
        verify_request_signature(
            timestamp=headers.get("x-lark-request-timestamp") or headers.get("X-Lark-Request-Timestamp") or "",
            nonce=headers.get("x-lark-request-nonce") or headers.get("X-Lark-Request-Nonce") or "",
            signature=headers.get("x-lark-signature") or headers.get("X-Lark-Signature") or "",
            encrypt_key=self.settings.feishu_encrypt_key,
            body=body,
        )

    async def on_bus_event(self, event: BusEvent) -> None:
        if event.channel != ChannelType.FEISHU:
            return
        task_id = event.task_id
        if event.event_type == EventType.TASK_STATUS:
            message = event.payload.get("message") or "处理中…"
            # Keep prior streamed text if any, append status line for visibility
            prior = self._buffers.get(task_id, "")
            display = f"{prior}\n\n⏳ {message}".strip() if prior else f"⏳ {message}"
            message_id = self._card_messages.get(task_id)
            if message_id:
                card = build_streaming_card("Nexus-Lark-Mind", display)
                await self.client.update_message_card(message_id, card)
            return
        if event.event_type == EventType.TASK_DELTA:
            delta = event.payload.get("delta") or ""
            async with self._lock:
                self._buffers[task_id] = self._buffers.get(task_id, "") + delta
                content = self._buffers[task_id]
            message_id = self._card_messages.get(task_id)
            if message_id:
                card = build_streaming_card("Nexus-Lark-Mind", content)
                await self.client.update_message_card(message_id, card)
        elif event.event_type == EventType.TASK_COMPLETED:
            content = event.payload.get("content") or self._buffers.get(task_id, "")
            message_id = self._card_messages.get(task_id)
            card = build_text_card(
                "Nexus-Lark-Mind",
                content,
                buttons=[
                    {"label": "再问一次", "action": "retry", "payload": content[:80]},
                    {"label": "清空会话", "action": "clear", "payload": event.session_id},
                ],
            )
            if message_id:
                await self.client.update_message_card(message_id, card)
            self._buffers.pop(task_id, None)
            self._card_messages.pop(task_id, None)
        elif event.event_type == EventType.TASK_FAILED:
            error = event.payload.get("error") or "unknown error"
            message_id = self._card_messages.get(task_id)
            # Friendlier rate-limit copy
            if "429" in error or "限流" in error:
                body = f"⚠️ {error}"
            else:
                body = f"任务失败：{error}"
            card = build_text_card("Nexus-Lark-Mind", body)
            if message_id:
                await self.client.update_message_card(message_id, card)
            self._buffers.pop(task_id, None)
            self._card_messages.pop(task_id, None)
