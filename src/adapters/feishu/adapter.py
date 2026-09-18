"""Feishu adapter — normalize events, stream card updates via event bus."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.adapters.base_adapter import BaseAdapter
from src.adapters.channels import resolve_feishu
from src.adapters.feishu.cards import (
    build_approval_card,
    build_ask_card,
    build_error_card,
    build_gate_resolved_card,
    build_model_pick_card,
    build_no_provider_card,
    build_plan_review_card,
    build_provider_pick_card,
    build_reply_card,
    build_session_cleared_card,
    build_streaming_card,
    build_text_card,
    default_reply_buttons,
    extract_citations,
    sanitize_error,
    summarize_tool_result,
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

# Feishu PATCH /im/v1/messages is easy to rate-limit during token streams.
STREAM_DEBOUNCE_S = 0.45
KB_TOOL_HINTS = ("kb_search", "kb_read", "kb_get", "weknora_search", "weknora_read")


@dataclass
class _TurnCard:
    content: str = ""
    status: str = ""
    tools: List[Dict[str, Any]] = field(default_factory=list)
    citations: str = ""
    user_preview: str = ""
    session_id: str = ""
    chat_id: str = ""
    flush_task: Optional[asyncio.Task] = None


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
        self._turns: Dict[str, _TurnCard] = {}
        self._last_prompts: Dict[str, str] = {}
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
            if data.kind == "conversation" or data.action in {"retry", "clear"}:
                return await self._handle_conversation_card(data)
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
            await self._seed_turn_card(task, chat_id=msg.chat_id, user_text=text.strip())
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
            template="green",
            subtitle="已就绪",
            icon_token="yes-outlined",
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
        await self._seed_turn_card(task, chat_id=chat_id, user_text=pending)
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
                "allow": "已允许这次工具调用。",
                "allow_session": "已允许，本会话后续同类工具将自动接受。",
                "deny": "已拒绝。",
                "submit": "已提交你的选择。",
                "approve": "已批准计划并开始执行。",
                "keep_planning": "继续规划中。",
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

    async def _handle_conversation_card(self, data: Any) -> Optional[StandardTask]:
        action = str(data.action or "").strip().lower()
        chat_id = str(data.chat_id or "").strip()
        session_id = str(data.session_id or "").strip() or (
            f"feishu:{chat_id}:{data.user_id}" if chat_id else f"feishu:{data.user_id}"
        )
        message_id = str(data.open_message_id or "").strip()
        if action == "clear":
            try:
                await self.orchestrator.call("DELETE", f"/rpc/sessions/{session_id}")
            except Exception:
                logger.exception("Failed to clear Feishu session %s", session_id)
            self._last_prompts.pop(session_id, None)
            if message_id:
                try:
                    await self.client.update_message_card(message_id, build_session_cleared_card())
                except Exception:
                    logger.exception("Failed to update cleared-session card")
            return None
        if action != "retry":
            return None
        text = str(data.payload or "").strip() or self._last_prompts.get(session_id, "")
        if not text:
            if message_id:
                await self.client.update_message_card(
                    message_id,
                    build_error_card("没有可重试的原文。请直接发送一条新消息。"),
                )
            return None
        await self._ensure_session(session_id, user_id=data.user_id)
        session = await self._get_session(session_id)
        task = StandardTask(
            session_id=session_id,
            channel=ChannelType.FEISHU,
            user_id=data.user_id,
            content=text,
            model_provider=str(session.get("model_provider") or "") or None,
            model_name=str(session.get("model_name") or "") or None,
            metadata={
                "feishu_open_message_id": message_id,
                "feishu_chat_id": chat_id,
                "card_action": "retry",
            },
        )
        await self._seed_turn_card(task, chat_id=chat_id, user_text=text)
        await self.submit(task)
        return task

    def _turn(self, task_id: str) -> _TurnCard:
        turn = self._turns.get(task_id)
        if turn is None:
            turn = _TurnCard()
            self._turns[task_id] = turn
        return turn

    async def _seed_turn_card(
        self,
        task: StandardTask,
        *,
        chat_id: str,
        user_text: str,
    ) -> None:
        preview = (user_text or "").strip()
        if preview:
            self._last_prompts[task.session_id] = preview
        turn = self._turn(task.task_id)
        turn.user_preview = preview
        turn.session_id = task.session_id
        turn.chat_id = chat_id
        if not chat_id:
            return
        card = build_streaming_card(
            "Nexus Lark Mind",
            "",
            status="生成中…",
            user_preview=preview,
        )
        sent = await self.client.send_card_to_chat(chat_id, card)
        message_id = (
            ((sent.get("data") or {}).get("message_id")) if isinstance(sent, dict) else None
        )
        if message_id:
            self._card_messages[task.task_id] = message_id

    def _upsert_tool(self, turn: _TurnCard, payload: Dict[str, Any], *, running: bool) -> None:
        name = str(payload.get("name") or payload.get("base") or "tool")
        call_id = str(payload.get("id") or payload.get("call_id") or name)
        status, summary = ("running", "") if running else summarize_tool_result(payload)
        row = {"id": call_id, "name": name, "status": status, "summary": summary}
        for i, existing in enumerate(turn.tools):
            if existing.get("id") == call_id or (
                existing.get("name") == name and existing.get("status") == "running"
            ):
                turn.tools[i] = {**existing, **row}
                return
        turn.tools.append(row)

    def _build_live_card(self, turn: _TurnCard) -> Dict[str, Any]:
        return build_streaming_card(
            "Nexus Lark Mind",
            turn.content,
            status=turn.status,
            tools=turn.tools,
            user_preview=turn.user_preview,
            citations=turn.citations,
        )

    async def _flush_turn_card(self, task_id: str) -> None:
        message_id = self._card_messages.get(task_id)
        turn = self._turns.get(task_id)
        if not message_id or turn is None:
            return
        try:
            await self.client.update_message_card(message_id, self._build_live_card(turn))
        except Exception:
            logger.exception("Failed to patch Feishu streaming card %s", message_id)

    def _schedule_turn_flush(self, task_id: str, *, immediate: bool = False) -> None:
        turn = self._turns.get(task_id)
        if turn is None:
            return
        pending = turn.flush_task
        if pending and not pending.done():
            pending.cancel()
        if immediate:
            turn.flush_task = asyncio.create_task(self._flush_turn_card(task_id))
            return

        async def _later() -> None:
            try:
                await asyncio.sleep(STREAM_DEBOUNCE_S)
                await self._flush_turn_card(task_id)
            except asyncio.CancelledError:
                return

        turn.flush_task = asyncio.create_task(_later())

    def _forget_turn(self, task_id: str) -> _TurnCard:
        turn = self._turns.pop(task_id, _TurnCard())
        if turn.flush_task and not turn.flush_task.done():
            turn.flush_task.cancel()
        self._card_messages.pop(task_id, None)
        return turn

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
        if event.event_type == EventType.TASK_TOOL_CALL:
            async with self._lock:
                turn = self._turn(task_id)
                self._upsert_tool(turn, event.payload, running=True)
                turn.status = f"正在调用 `{event.payload.get('name') or 'tool'}`"
            self._schedule_turn_flush(task_id, immediate=True)
            return
        if event.event_type == EventType.TASK_TOOL_RESULT:
            async with self._lock:
                turn = self._turn(task_id)
                self._upsert_tool(turn, event.payload, running=False)
                cites = extract_citations(event.payload)
                if cites:
                    turn.citations = cites
                name = str(event.payload.get("name") or "")
                if any(hint in name for hint in KB_TOOL_HINTS) and cites:
                    turn.status = "知识库命中已写入卡片"
                else:
                    turn.status = ""
            self._schedule_turn_flush(task_id, immediate=True)
            return
        if event.event_type == EventType.TASK_STATUS:
            message = str(event.payload.get("message") or "处理中…").strip()
            async with self._lock:
                turn = self._turn(task_id)
                turn.status = message
            self._schedule_turn_flush(task_id)
            return
        if event.event_type == EventType.TASK_DELTA:
            delta = event.payload.get("delta") or ""
            so_far = event.payload.get("content_so_far")
            async with self._lock:
                turn = self._turn(task_id)
                if isinstance(so_far, str) and so_far:
                    turn.content = so_far
                else:
                    turn.content = (turn.content or "") + str(delta)
            self._schedule_turn_flush(task_id)
            return
        if event.event_type == EventType.TASK_COMPLETED:
            message_id = self._card_messages.get(task_id)
            turn = self._forget_turn(task_id)
            content = event.payload.get("content") or turn.content
            card = build_reply_card(
                str(content or ""),
                citations=turn.citations,
                tools=turn.tools,
                user_preview=turn.user_preview,
                buttons=default_reply_buttons(
                    session_id=event.session_id,
                    chat_id=turn.chat_id or _feishu_chat_id(event.session_id),
                    retry_text=self._last_prompts.get(event.session_id, "")
                    or turn.user_preview,
                ),
            )
            if message_id:
                try:
                    await self.client.update_message_card(message_id, card)
                except Exception:
                    logger.exception("Failed to finalize Feishu reply card")
            return
        if event.event_type == EventType.TASK_FAILED:
            message_id = self._card_messages.get(task_id)
            turn = self._forget_turn(task_id)
            error = str(event.payload.get("error") or "unknown error")
            rate_limited = "429" in error or "限流" in error
            chat_id = turn.chat_id or _feishu_chat_id(event.session_id)
            card = build_error_card(
                sanitize_error(error),
                rate_limited=rate_limited,
                buttons=default_reply_buttons(
                    session_id=event.session_id,
                    chat_id=chat_id,
                    retry_text=self._last_prompts.get(event.session_id, "")
                    or turn.user_preview,
                ),
            )
            if message_id:
                try:
                    await self.client.update_message_card(message_id, card)
                except Exception:
                    logger.exception("Failed to finalize Feishu error card")
