"""WeCom (企业微信) adapter."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

from src.adapters import im_crypto
from src.adapters.base_adapter import BaseAdapter
from src.adapters.channels import resolve_wecom
from src.adapters.wecom.client import WeComClient
from src.adapters.wecom import events as wc_events
from src.common.config import Settings, get_settings
from src.common.errors import ValidationAppError
from src.common.rpc_client import RpcClient
from src.common.schemas import BusEvent, ChannelType, EventType, StandardTask
from src.infrastructure.redis_client import RedisClient

logger = logging.getLogger(__name__)


def _wecom_user(session_id: str) -> str:
    parts = str(session_id or "").split(":", 2)
    if len(parts) >= 3 and parts[0] == "wecom":
        return parts[2]
    if len(parts) == 2 and parts[0] == "wecom":
        return parts[1]
    return ""


class WeComAdapter(BaseAdapter):
    channel = ChannelType.WECOM

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
        self.client = WeComClient(self.settings)
        self._buffers: Dict[str, str] = {}
        self._lock = asyncio.Lock()

    def verify_signature(
        self,
        *,
        msg_signature: str,
        timestamp: str,
        nonce: str,
        encrypt: str,
    ) -> None:
        creds = resolve_wecom(self.settings)
        if not creds.token:
            return
        ok = im_crypto.verify_signature(
            token=creds.token,
            timestamp=timestamp,
            nonce=nonce,
            encrypt=encrypt,
            signature=msg_signature,
        )
        if not ok:
            raise ValidationAppError("wecom signature invalid")

    def decrypt_echo(self, echostr: str) -> str:
        creds = resolve_wecom(self.settings)
        if not creds.encoding_aes_key:
            return echostr
        return im_crypto.decrypt_payload(
            encoding_aes_key=creds.encoding_aes_key,
            receive_id=creds.corp_id,
            encrypt_b64=echostr,
        )

    def decode_post_xml(self, body: str) -> Dict[str, str]:
        creds = resolve_wecom(self.settings)
        encrypt = wc_events.extract_encrypt_from_xml(body)
        if encrypt and creds.encoding_aes_key:
            plain = wc_events.decrypt_post_body(
                encoding_aes_key=creds.encoding_aes_key,
                corp_id=creds.corp_id,
                encrypt_b64=encrypt,
            )
            return wc_events.parse_xml(plain)
        return wc_events.parse_xml(body)

    async def handle_inbound_fields(self, fields: Dict[str, str]) -> Optional[StandardTask]:
        kind, data = wc_events.classify_xml(fields)
        if kind != "message":
            return None
        msg: wc_events.WeComMessage = data
        text = (msg.text or "").strip()
        if not text or not msg.user_id:
            return None
        session_id = f"wecom:{msg.agent_id or 'agent'}:{msg.user_id}"
        await self._ensure_session(session_id, user_id=msg.user_id)
        task = StandardTask(
            session_id=session_id,
            channel=ChannelType.WECOM,
            user_id=msg.user_id,
            content=text,
            metadata={
                "wecom_agent_id": msg.agent_id,
                "wecom_msg_id": msg.msg_id,
            },
        )
        await self.submit(task)
        return task

    async def handle_inbound(self, payload: Dict[str, Any]) -> Optional[StandardTask]:
        # Compatibility with BaseAdapter; prefer handle_inbound_fields for XML.
        if "Content" in payload or "MsgType" in payload:
            fields = {str(k): str(v) for k, v in payload.items()}
            return await self.handle_inbound_fields(fields)
        return None

    async def _ensure_session(self, session_id: str, *, user_id: str) -> None:
        if self.kernel is None:
            return
        try:
            await self.kernel.call(
                "POST",
                "/rpc/sessions/ensure",
                json={"session_id": session_id, "user_id": user_id, "channel": "wecom"},
            )
        except Exception:
            logger.debug("wecom ensure session soft-fail", exc_info=True)

    async def _deliver(self, session_id: str, text: str) -> None:
        user_id = _wecom_user(session_id)
        if not user_id:
            logger.warning("wecom deliver missing user session=%s", session_id)
            return
        try:
            await self.client.send_text(user_id=user_id, text=text)
        except Exception:
            logger.exception("wecom send failed user=%s", user_id)

    async def on_bus_event(self, event: BusEvent) -> None:
        channel = event.channel.value if hasattr(event.channel, "value") else str(event.channel)
        if channel != ChannelType.WECOM.value:
            return
        task_id = event.task_id
        if event.event_type == EventType.TASK_DELTA:
            delta = event.payload.get("delta") or ""
            async with self._lock:
                self._buffers[task_id] = self._buffers.get(task_id, "") + delta
            return
        if event.event_type == EventType.TASK_COMPLETED:
            content = event.payload.get("content") or self._buffers.get(task_id, "")
            await self._deliver(event.session_id, content or "(完成)")
            self._buffers.pop(task_id, None)
        elif event.event_type == EventType.TASK_FAILED:
            error = event.payload.get("error") or "unknown error"
            await self._deliver(event.session_id, f"任务失败：{error}")
            self._buffers.pop(task_id, None)
        elif event.event_type in {
            EventType.TASK_TOOL_APPROVAL,
            EventType.TASK_ASK_USER,
            EventType.TASK_PLAN_REVIEW,
        }:
            await self._deliver(
                event.session_id,
                f"需要在 Web 控制台处理人机交互（{event.event_type.value}）。打开 Nexus Lark Mind 继续。",
            )
