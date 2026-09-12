"""Feishu adapter — normalize events, stream card updates via event bus."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from src.adapters.base_adapter import BaseAdapter
from src.adapters.channels import resolve_feishu
from src.adapters.feishu.cards import (
    build_approval_card,
    build_ask_card,
    build_gate_resolved_card,
    build_model_pick_card,
    build_no_provider_card,
    build_plan_review_card,
    build_provider_pick_card,
    build_streaming_card,
    build_text_card,
)
from src.adapters.feishu.client import FeishuClient
from src.adapters.feishu.crypto import AESCipher, verify_request_signature, verify_token
from src.adapters.feishu.events import classify_payload, strip_mention_placeholders
from src.adapters.feishu.model_pick import (
    catalog_choices,
    is_rebind_command,
    session_has_model,
)
from src.common.config import Settings, get_settings
from src.common.rpc_client import RpcClient
from src.common.schemas import BusEvent, ChannelType, EventType, StandardTask
from src.infrastructure.redis_client import RedisClient

logger = logging.getLogger(__name__)


def _feishu_chat_id(session_id: str) -> str:
    """Parse chat id from `feishu:{chat_id}:{user_id}` session keys."""
    parts = str(session_id or "").split(":", 2)
    if len(parts) >= 3 and parts[0] == "feishu":
        return parts[1]
    return ""


class FeishuAdapter(BaseAdapter):
    channel = ChannelType.FEISHU

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
        self.client = FeishuClient(self.settings)
        self._card_messages: Dict[str, str] = {}  # task_id -> feishu message_id
        self._gate_messages: Dict[str, str] = {}  # call_id -> feishu message_id
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
            if data.kind in {"approval", "ask_user", "plan_review"} and data.call_id:
                await self._resolve_hitl_card(data)
                return None
            if data.kind in {"provider_pick", "model_pick"}:
                await self._handle_model_pick_card(data)
                return None
            action = data.action
            text = f"[card_action:{action}] {data.payload}".strip()
            chat_id = str(data.chat_id or "").strip()
            session_id = str(data.session_id or "").strip() or (
                f"feishu:{chat_id}:{data.user_id}" if chat_id else f"feishu:{data.user_id}"
            )
            task = StandardTask(
                session_id=session_id,
                channel=ChannelType.FEISHU,
                user_id=data.user_id,
                content=text,
                metadata={
                    "feishu_open_message_id": data.open_message_id,
                    "feishu_chat_id": chat_id,
                    "card_action": action,
                },
            )
            await self.submit(task)
            return task
        if kind == "message":
            msg = data
            chat_type = (msg.chat_type or "").lower()
            # Group chats: only reply when the bot is @mentioned.
            # P2P / unknown: always accept (DM to bot).
            if chat_type == "group" and not msg.mentioned_bot:
                logger.info(
                    "Ignore feishu group message without @bot chat=%s msg=%s",
                    msg.chat_id,
                    msg.message_id,
                )
                return None
            text = strip_mention_placeholders(msg.text) or msg.text
            if not text.strip():
                logger.debug("Ignore empty feishu message after stripping mentions")
                return None
            session_id = f"feishu:{msg.chat_id}:{msg.user_id}"
            await self._ensure_session(session_id, user_id=msg.user_id)

            if is_rebind_command(text):
                await self._patch_session(
                    session_id,
                    {
                        "model_provider": "",
                        "model_name": "",
                        "clear_pending_user_text": True,
                    },
                )
                await self._send_provider_gate(session_id, msg.chat_id, pending_text="")
                return None

            session = await self._get_session(session_id)
            if not session_has_model(session):
                # Required: bind provider/model for this Feishu conversation first.
                await self._send_provider_gate(session_id, msg.chat_id, pending_text=text.strip())
                return None

            task = StandardTask(
                session_id=session_id,
                channel=ChannelType.FEISHU,
                user_id=msg.user_id,
                content=text,
                model_provider=str(session.get("model_provider") or "") or None,
                model_name=str(session.get("model_name") or "") or None,
                metadata={
                    "feishu_message_id": msg.message_id,
                    "feishu_chat_id": msg.chat_id,
                    "feishu_chat_type": chat_type or "unknown",
                    "feishu_mentioned_bot": bool(msg.mentioned_bot),
                },
            )
            # Seed streaming card
            if msg.chat_id:
                card = build_streaming_card("Nexus Lark Mind", "")
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

    async def _ensure_session(self, session_id: str, *, user_id: str) -> Dict[str, Any]:
        try:
            data = await self.orchestrator.call(
                "POST",
                "/rpc/sessions",
                json={"session_id": session_id, "user_id": user_id, "channel": "feishu"},
            )
            return data if isinstance(data, dict) else {}
        except Exception:
            logger.exception("Failed to ensure Feishu session %s", session_id)
            return {}

    async def _get_session(self, session_id: str) -> Dict[str, Any]:
        try:
            data = await self.orchestrator.call("GET", f"/rpc/sessions/{session_id}")
            return data if isinstance(data, dict) else {}
        except Exception:
            logger.exception("Failed to load Feishu session %s", session_id)
            return {}

    async def _patch_session(self, session_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
        try:
            data = await self.orchestrator.call(
                "PATCH",
                f"/rpc/sessions/{session_id}/interaction",
                json={**body, "user_id": body.get("user_id") or "feishu-user", "channel": "feishu"},
            )
            return data if isinstance(data, dict) else {}
        except Exception:
            logger.exception("Failed to patch Feishu session %s", session_id)
            return {}

    async def _fetch_catalog_choices(self) -> List[Dict[str, Any]]:
        if self.kernel is None:
            return []
        try:
            data = await self.kernel.call(
                "GET",
                "/rpc/providers",
                params={"configured_only": "true"},
            )
            return catalog_choices(data if isinstance(data, dict) else {})
        except Exception:
            logger.exception("Failed to load provider catalog for Feishu pick")
            return []

    async def _send_provider_gate(
        self,
        session_id: str,
        chat_id: str,
        *,
        pending_text: str,
        page: int = 0,
        message_id: str = "",
    ) -> None:
        if pending_text:
            await self._patch_session(session_id, {"pending_user_text": pending_text})
        choices = await self._fetch_catalog_choices()
        if not choices:
            card = build_no_provider_card()
        else:
            card = build_provider_pick_card(
                providers=choices,
                session_id=session_id,
                chat_id=chat_id,
                page=page,
            )
        await self._deliver_pick_card(chat_id, card, message_id=message_id)

    async def _send_model_gate(
        self,
        *,
        session_id: str,
        chat_id: str,
        provider_id: str,
        page: int = 0,
        message_id: str = "",
    ) -> None:
        choices = await self._fetch_catalog_choices()
        entry = next((p for p in choices if p["id"] == provider_id), None)
        if entry is None:
            await self._send_provider_gate(
                session_id, chat_id, pending_text="", page=0, message_id=message_id
            )
            return
        models = list(entry.get("models") or [])
        if len(models) == 1:
            await self._bind_and_flush(
                session_id=session_id,
                chat_id=chat_id,
                user_id=session_id.rsplit(":", 1)[-1],
                provider_id=provider_id,
                model_name=models[0],
                message_id=message_id,
            )
            return
        card = build_model_pick_card(
            provider_id=provider_id,
            provider_label=str(entry.get("label") or provider_id),
            models=models,
            session_id=session_id,
            chat_id=chat_id,
            page=page,
        )
        await self._deliver_pick_card(chat_id, card, message_id=message_id)

    async def _deliver_pick_card(
        self,
        chat_id: str,
        card: Dict[str, Any],
        *,
        message_id: str = "",
    ) -> None:
        if not chat_id:
            return
        try:
            if message_id:
                await self.client.update_message_card(message_id, card)
            else:
                await self.client.send_card_to_chat(chat_id, card)
        except Exception:
            logger.exception("Failed to deliver Feishu model-pick card")

    async def _handle_model_pick_card(self, data: Any) -> None:
        chat_id = str(data.chat_id or "").strip()
        session_id = str(data.session_id or "").strip()
        if not session_id and chat_id:
            session_id = f"feishu:{chat_id}:{data.user_id}"
        if not session_id:
            logger.warning("Feishu model pick missing session_id")
            return
        await self._ensure_session(session_id, user_id=data.user_id)
        action = str(data.action or "").strip().lower()
        message_id = str(data.open_message_id or "").strip()
        page = int(getattr(data, "page", 0) or 0)

        if action in {"page_providers", "back_providers"}:
            await self._send_provider_gate(
                session_id,
                chat_id,
                pending_text="",
                page=page,
                message_id=message_id,
            )
            return
        if action == "pick_provider":
            provider_id = str(data.provider_id or "").strip()
            if not provider_id:
                return
            await self._send_model_gate(
                session_id=session_id,
                chat_id=chat_id,
                provider_id=provider_id,
                page=0,
                message_id=message_id,
            )
            return
        if action == "page_models":
            provider_id = str(data.provider_id or "").strip()
            if not provider_id:
                return
            await self._send_model_gate(
                session_id=session_id,
                chat_id=chat_id,
                provider_id=provider_id,
                page=page,
                message_id=message_id,
            )
            return
        if action == "pick_model":
            provider_id = str(data.provider_id or "").strip()
            model_name = str(data.model_name or "").strip()
            if not provider_id or not model_name:
                return
            await self._bind_and_flush(
                session_id=session_id,
                chat_id=chat_id,
                user_id=data.user_id,
                provider_id=provider_id,
                model_name=model_name,
                message_id=message_id,
            )

    async def _bind_and_flush(
        self,
        *,
        session_id: str,
        chat_id: str,
        user_id: str,
        provider_id: str,
        model_name: str,
        message_id: str = "",
    ) -> None:
        session = await self._get_session(session_id)
        pending = str((session or {}).get("pending_user_text") or "").strip()
        await self._patch_session(
            session_id,
            {
                "model_provider": provider_id,
                "model_name": model_name,
                "clear_pending_user_text": True,
                "user_id": user_id,
            },
        )
        bound_card = build_text_card(
            "已绑定模型",
            f"本对话将使用 **`{provider_id}` / `{model_name}`**。\n\n"
            + ("正在处理你刚才的消息…" if pending else "直接发送下一条消息即可。"),
        )
        await self._deliver_pick_card(chat_id, bound_card, message_id=message_id)
        if not pending:
            return
        task = StandardTask(
            session_id=session_id,
            channel=ChannelType.FEISHU,
            user_id=user_id,
            content=pending,
            model_provider=provider_id,
            model_name=model_name,
            metadata={
                "feishu_chat_id": chat_id,
                "feishu_model_bound": True,
            },
        )
        if chat_id:
            stream_card = build_streaming_card("Nexus Lark Mind", "")
            sent = await self.client.send_card_to_chat(chat_id, stream_card)
            mid = ((sent.get("data") or {}).get("message_id")) if isinstance(sent, dict) else None
            if mid:
                self._card_messages[task.task_id] = mid
        await self.submit(task)

    async def _resolve_hitl_card(self, data: Any) -> None:
        if self.kernel is None:
            logger.warning("Feishu HITL resolve skipped — kernel RPC not wired")
            return
        action = str(data.action or "deny").strip().lower()
        call_id = str(data.call_id or "").strip()
        if data.kind == "approval":
            payload: Dict[str, Any] = {"action": action, "reason": "feishu_card"}
            if action in {"allow_session", "always"}:
                payload["action"] = "allow_session"
            elif action not in {"allow", "deny"}:
                payload["action"] = "deny"
        elif data.kind == "plan_review":
            act = action if action in {"approve", "keep_planning", "deny"} else "deny"
            payload = {
                "action": act,
                "feedback": "",
                "reason": "feishu_card",
            }
        else:
            payload = {
                "action": action if action in {"submit", "deny"} else "submit",
                "answers": data.answers if isinstance(data.answers, dict) else {},
                "reason": "feishu_card",
            }
            if action == "deny":
                payload["action"] = "deny"
        try:
            await self.kernel.call(
                "POST",
                "/rpc/gates/resolve",
                json={"call_id": call_id, "payload": payload},
            )
        except Exception:
            logger.exception("Feishu gate resolve failed call_id=%s", call_id)
            return
        message_id = data.open_message_id or self._gate_messages.pop(call_id, "")
        if message_id:
            label = {
                "allow": "已允许",
                "allow_session": "已允许（本会话自动接受）",
                "deny": "已拒绝",
                "submit": "已提交回答",
                "approve": "已批准计划并开始执行",
                "keep_planning": "继续规划",
            }.get(payload.get("action") or action, "已处理")
            try:
                await self.client.update_message_card(
                    message_id,
                    build_gate_resolved_card("已处理", label),
                )
            except Exception:
                logger.exception("Failed to update Feishu gate card %s", message_id)

    def decode_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        creds = resolve_feishu(self.settings)
        if "encrypt" in payload and creds.encrypt_key:
            return AESCipher(creds.encrypt_key).decrypt(payload["encrypt"])
        return payload

    def verify(self, payload: Dict[str, Any], *, headers: Dict[str, str], body: str) -> None:
        creds = resolve_feishu(self.settings)
        verify_token(payload, creds.verification_token)
        verify_request_signature(
            timestamp=headers.get("x-lark-request-timestamp") or headers.get("X-Lark-Request-Timestamp") or "",
            nonce=headers.get("x-lark-request-nonce") or headers.get("X-Lark-Request-Nonce") or "",
            signature=headers.get("x-lark-signature") or headers.get("X-Lark-Signature") or "",
            encrypt_key=creds.encrypt_key,
            body=body,
        )

    async def _send_gate_card(self, session_id: str, call_id: str, card: Dict[str, Any]) -> None:
        chat_id = _feishu_chat_id(session_id)
        if not chat_id:
            logger.warning("No Feishu chat_id for session %s — cannot send HITL card", session_id)
            return
        try:
            sent = await self.client.send_card_to_chat(chat_id, card)
            message_id = (
                ((sent.get("data") or {}).get("message_id")) if isinstance(sent, dict) else None
            )
            if message_id and call_id:
                self._gate_messages[call_id] = message_id
        except Exception:
            logger.exception("Failed to send Feishu HITL card call_id=%s", call_id)

    async def on_bus_event(self, event: BusEvent) -> None:
        # Hard channel isolation: web/system tasks must never update Feishu cards.
        channel = event.channel.value if hasattr(event.channel, "value") else str(event.channel)
        if channel != ChannelType.FEISHU.value:
            return
        task_id = event.task_id
        if event.event_type == EventType.TASK_TOOL_APPROVAL:
            call_id = str(event.payload.get("call_id") or event.payload.get("id") or "")
            card = build_approval_card(
                call_id=call_id,
                name=str(event.payload.get("name") or ""),
                base=str(event.payload.get("base") or ""),
                arguments=event.payload.get("arguments"),
            )
            await self._send_gate_card(event.session_id, call_id, card)
            return
        if event.event_type == EventType.TASK_ASK_USER:
            call_id = str(event.payload.get("call_id") or event.payload.get("id") or "")
            card = build_ask_card(
                call_id=call_id,
                title=str(event.payload.get("title") or ""),
                questions=event.payload.get("questions") or [],
            )
            await self._send_gate_card(event.session_id, call_id, card)
            return
        if event.event_type == EventType.TASK_PLAN_REVIEW:
            call_id = str(event.payload.get("call_id") or event.payload.get("id") or "")
            card = build_plan_review_card(
                call_id=call_id,
                title=str(event.payload.get("title") or "计划审阅"),
                plan=str(event.payload.get("plan") or ""),
            )
            await self._send_gate_card(event.session_id, call_id, card)
            return
        if event.event_type == EventType.TASK_STATUS:
            message = event.payload.get("message") or "处理中…"
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
            if "429" in error or "限流" in error:
                body = f"⚠️ {error}"
            else:
                body = f"任务失败：{error}"
            card = build_text_card("Nexus-Lark-Mind", body)
            if message_id:
                await self.client.update_message_card(message_id, card)
            self._buffers.pop(task_id, None)
            self._card_messages.pop(task_id, None)
