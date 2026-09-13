"""DingTalk adapter — robot HTTP inbound + bus text outbound."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

from src.adapters.base_adapter import BaseAdapter
from src.adapters.channels import resolve_dingtalk
from src.adapters.dingtalk.client import DingTalkClient
from src.adapters.dingtalk import events as dt_events
from src.adapters import im_crypto
from src.common.config import Settings, get_settings
from src.common.errors import ValidationAppError
from src.common.rpc_client import RpcClient
from src.common.schemas import BusEvent, ChannelType, EventType, StandardTask
from src.infrastructure.redis_client import RedisClient

logger = logging.getLogger(__name__)


def _dingtalk_ids(session_id: str) -> tuple[str, str]:
    parts = str(session_id or "").split(":", 2)
    if len(parts) >= 3 and parts[0] == "dingtalk":
        return parts[1], parts[2]
    return "", ""


class DingTalkAdapter(BaseAdapter):
    channel = ChannelType.DINGTALK

    def __init__(
        self,
        orchestrator: RpcClient,
        redis_client: RedisClient,
        settings: Optional[Settings] = None,
        kernel: Optional[RpcClient] = None,
    ) -> None:
        super().__init__(orchestrator, redis_client)
        self.settings = settings or get_settings()
        self.kernel = kernel
        self.client = DingTalkClient(self.settings)
        self._webhooks: Dict[str, str] = {}  # task_id -> sessionWebhook
        self._buffers: Dict[str, str] = {}
        self._user_ids: Dict[str, str] = {}  # task_id -> user_id
        self._lock = asyncio.Lock()

    def verify_request(
        self,
        *,
        timestamp: str,
        nonce: str,
        signature: str,
        encrypt: str = "",
    ) -> None:
        creds = resolve_dingtalk(self.settings)
        if not creds.token:
            return
        ok = im_crypto.verify_signature(
            token=creds.token,
            timestamp=timestamp,
            nonce=nonce,
            encrypt=encrypt,
            signature=signature,
        )
        if not ok:
            raise ValidationAppError("dingtalk signature invalid")

    def decode_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        creds = resolve_dingtalk(self.settings)
        return dt_events.decrypt_if_needed(
            payload,
            encoding_aes_key=creds.encoding_aes_key,
            receive_id=creds.client_id,
        )

    async def handle_inbound(self, payload: Dict[str, Any]) -> Optional[StandardTask]:
        kind, data = dt_events.classify_payload(payload)
        if kind in {"url_verification", "ignore", "encrypted"}:
            return None
        if kind != "message":
            return None
        msg: dt_events.DingTalkMessage = data
        text = (msg.text or "").strip()
        if not text:
            return None
        session_id = f"dingtalk:{msg.conversation_id}:{msg.user_id}"
        await self._ensure_session(session_id, user_id=msg.user_id)
        task = StandardTask(
            session_id=session_id,
            channel=ChannelType.DINGTALK,
            user_id=msg.user_id,
            content=text,
            metadata={
                "dingtalk_conversation_id": msg.conversation_id,
                "dingtalk_session_webhook": msg.session_webhook,
                "dingtalk_message_id": msg.message_id,
            },
        )
        if msg.session_webhook:
            self._webhooks[task.task_id] = msg.session_webhook
        self._user_ids[task.task_id] = msg.user_id
        await self.submit(task)
        return task

    async def _ensure_session(self, session_id: str, *, user_id: str) -> None:
        if self.kernel is None:
            return
        try:
            await self.kernel.call(
                "POST",
                "/rpc/sessions/ensure",
                json={"session_id": session_id, "user_id": user_id, "channel": "dingtalk"},
            )
        except Exception:
            logger.debug("dingtalk ensure session soft-fail", exc_info=True)

    async def _deliver(self, task_id: str, session_id: str, text: str) -> None:
        webhook = self._webhooks.get(task_id)
        if webhook:
            try:
                await self.client.reply_session_webhook(webhook, text)
                return
            except Exception:
                logger.exception("dingtalk sessionWebhook reply failed")
        _, user_id = _dingtalk_ids(session_id)
        user_id = user_id or self._user_ids.get(task_id, "")
        if user_id:
            try:
                await self.client.send_text_to_user(user_id=user_id, text=text)
            except Exception:
                logger.exception("dingtalk proactive send failed user=%s", user_id)

    async def on_bus_event(self, event: BusEvent) -> None:
        channel = event.channel.value if hasattr(event.channel, "value") else str(event.channel)
        if channel != ChannelType.DINGTALK.value:
            return
        task_id = event.task_id
        if event.event_type == EventType.TASK_DELTA:
            delta = event.payload.get("delta") or ""
            async with self._lock:
                self._buffers[task_id] = self._buffers.get(task_id, "") + delta
            return
        if event.event_type == EventType.TASK_COMPLETED:
            content = event.payload.get("content") or self._buffers.get(task_id, "")
            await self._deliver(task_id, event.session_id, content or "(完成)")
            self._buffers.pop(task_id, None)
            self._webhooks.pop(task_id, None)
            self._user_ids.pop(task_id, None)
        elif event.event_type == EventType.TASK_FAILED:
            error = event.payload.get("error") or "unknown error"
            await self._deliver(task_id, event.session_id, f"任务失败：{error}")
            self._buffers.pop(task_id, None)
            self._webhooks.pop(task_id, None)
            self._user_ids.pop(task_id, None)
        elif event.event_type in {
            EventType.TASK_TOOL_APPROVAL,
            EventType.TASK_ASK_USER,
            EventType.TASK_PLAN_REVIEW,
        }:
            kind = event.event_type.value
            await self._deliver(
                task_id,
                event.session_id,
                f"需要在 Web 控制台处理人机交互（{kind}）。打开 Nexus Lark Mind 继续。",
            )
