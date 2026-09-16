"""Task dispatcher — consumes queue, calls kernel RPC, publishes stream events."""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, Optional, Set

from src.agent_orchestrator.queue_service import QueueService
from src.agent_orchestrator.session_context import SessionContext
from src.common.rpc_client import RpcClient
from src.common.schemas import (
    BusEvent,
    ChannelType,
    ChatMessage,
    ChatRole,
    EventType,
    StandardTask,
    TaskStatus,
    new_id,
)
from src.infrastructure.redis_client import RedisClient

logger = logging.getLogger(__name__)


class TaskDispatcher:
    def __init__(
        self,
        queue: QueueService,
        sessions: SessionContext,
        kernel: RpcClient,
        redis_client: RedisClient,
    ) -> None:
        self.queue = queue
        self.sessions = sessions
        self.kernel = kernel
        self.redis = redis_client
        self._running = False
        self._cancelled: Set[str] = set()
        self._abort_events: Dict[str, asyncio.Event] = {}
        self._session_task: Dict[str, str] = {}

    async def start_loop(self) -> None:
        self._running = True
        logger.info("Task dispatcher loop started")
        while self._running:
            task = await self.queue.dequeue(timeout=2)
            if task is None:
                continue
            try:
                await self.dispatch(task)
            except Exception as exc:
                logger.exception("Dispatch failed for task %s", task.task_id)
                detail = str(exc).strip() or exc.__class__.__name__
                nested = getattr(exc, "detail", None)
                if isinstance(nested, dict):
                    err_obj = nested.get("error")
                    if isinstance(err_obj, dict) and err_obj.get("message"):
                        detail = str(err_obj["message"]).strip() or detail
                    elif nested.get("message"):
                        detail = str(nested["message"]).strip() or detail
                elif isinstance(nested, str) and nested.strip():
                    detail = nested.strip()
                if len(detail) > 500:
                    detail = detail[:500] + "…"
                await self._publish(
                    task,
                    EventType.TASK_FAILED,
                    {
                        "error": detail,
                        "error_type": exc.__class__.__name__,
                    },
                )

    def stop(self) -> None:
        self._running = False

    def request_cancel(self, task_id: str) -> bool:
        """Mark task cancelled; aborts in-flight stream if active."""
        self._cancelled.add(task_id)
        ev = self._abort_events.get(task_id)
        if ev:
            ev.set()
            return True
        return task_id in self._cancelled

    def cancel_session(self, session_id: str) -> Optional[str]:
        task_id = self._session_task.get(session_id)
        if not task_id:
            return None
        self.request_cancel(task_id)
        return task_id

    def is_cancelled(self, task_id: str) -> bool:
        return task_id in self._cancelled

    async def dispatch(self, task: StandardTask) -> None:
        if self.is_cancelled(task.task_id):
            await self._publish(
                task,
                EventType.TASK_FAILED,
                {"error": "cancelled", "cancelled": True},
            )
            self._cancelled.discard(task.task_id)
            return

        task.status = TaskStatus.RUNNING
        self._session_task[task.session_id] = task.task_id
        abort = asyncio.Event()
        self._abort_events[task.task_id] = abort

        await self.sessions.ensure(
            task.session_id,
            user_id=task.user_id,
            channel=task.channel.value,
            cwd=(task.metadata or {}).get("cwd"),
            workspace_id=(task.metadata or {}).get("workspace_id"),
            workspace_title=(task.metadata or {}).get("workspace_title"),
            workspace_kind=(task.metadata or {}).get("workspace_kind"),
            ssh_host_id=(task.metadata or {}).get("ssh_host_id"),
        )

        session = await self.sessions.redis.get_session(task.session_id) or {}
        cwd = (session.get("cwd") or task.metadata.get("cwd") or "").strip()
        agent_mode = (
            (task.metadata or {}).get("agent_mode")
            or session.get("agent_mode")
            or "agent"
        )
        auto_accept = (task.metadata or {}).get("auto_accept")
        if auto_accept is None:
            auto_accept = bool(session.get("auto_accept"))
        multitask = (task.metadata or {}).get("multitask")
        if multitask is None:
            multitask = True
        permission_preset = (
            (task.metadata or {}).get("permission_preset")
            or session.get("permission_preset")
            or "workspace-write"
        )
        plan_enforcement = (
            (task.metadata or {}).get("plan_enforcement")
            or session.get("plan_enforcement")
            or "hard"
        )
        experience_tier = (
            (task.metadata or {}).get("experience_tier")
            or session.get("experience_tier")
            or "balanced"
        )
        reasoning_effort = (
            (task.metadata or {}).get("reasoning_effort")
            or session.get("reasoning_effort")
            or "medium"
        )
        # Feishu (and other channels) bind provider/model on the session;
        # fill task fields when the inbound payload left them empty.
        if not (task.model_provider or "").strip():
            bound = str(session.get("model_provider") or "").strip()
            if bound:
                task.model_provider = bound
        if not (task.model_name or "").strip():
            bound_model = str(session.get("model_name") or "").strip()
            if bound_model:
                task.model_name = bound_model
        task.metadata = {
            **(task.metadata or {}),
            "agent_mode": str(agent_mode).strip().lower() if agent_mode else "agent",
            "auto_accept": bool(auto_accept),
            "multitask": bool(multitask),
            "plan_status": session.get("plan_status") or "idle",
            "permission_preset": str(permission_preset).strip().lower(),
            "plan_enforcement": str(plan_enforcement).strip().lower(),
            "experience_tier": str(experience_tier).strip().lower(),
            "reasoning_effort": str(reasoning_effort).strip().lower(),
        }
        if cwd:
            task.metadata = {
                **task.metadata,
                "cwd": cwd,
                "workspace_id": session.get("workspace_id") or task.metadata.get("workspace_id") or "",
                "workspace_title": session.get("workspace_title")
                or task.metadata.get("workspace_title")
                or "",
                "workspace_kind": session.get("workspace_kind")
                or task.metadata.get("workspace_kind")
                or "local",
                "ssh_host_id": session.get("ssh_host_id") or task.metadata.get("ssh_host_id") or "",
            }

        history = await self.sessions.load_messages(task.session_id)
        messages = []
        for m in history:
            role = m.get("role")
            if role not in {"system", "user", "assistant", "tool"}:
                continue
            messages.append(
                ChatMessage(
                    role=ChatRole(role),
                    content=m.get("content") or "",
                    name=m.get("name"),
                    tool_call_id=m.get("tool_call_id"),
                    metadata=m.get("metadata") or {},
                )
            )
        messages.append(ChatMessage(role=ChatRole.USER, content=task.content))
        task.messages = messages

        await self._publish(task, EventType.TASK_STARTED, {})
        await self.sessions.append(task.session_id, ChatMessage(role=ChatRole.USER, content=task.content))
        await self.sessions.touch_title(task.session_id, task.content)

        try:
            if self.is_cancelled(task.task_id):
                await self._publish(
                    task,
                    EventType.TASK_FAILED,
                    {"error": "cancelled", "cancelled": True},
                )
                return
            if task.stream:
                await self._dispatch_stream(task, abort)
            else:
                await self._dispatch_complete(task)
        finally:
            self._abort_events.pop(task.task_id, None)
            self._cancelled.discard(task.task_id)
            if self._session_task.get(task.session_id) == task.task_id:
                self._session_task.pop(task.session_id, None)

    async def _dispatch_complete(self, task: StandardTask) -> None:
        data = await self.kernel.call(
            "POST",
            "/rpc/chat/run",
            json={"task": task.model_dump(mode="json")},
        )
        content = data.get("content") or ""
        await self.sessions.append(
            task.session_id,
            ChatMessage(role=ChatRole.ASSISTANT, content=content),
        )
        await self._publish(
            task,
            EventType.TASK_COMPLETED,
            {"content": content, "provider": data.get("provider"), "model": data.get("model")},
        )

    async def _dispatch_stream(self, task: StandardTask, abort: asyncio.Event) -> None:
        collected = ""
        reasoning_collected = ""
        error: Optional[str] = None
        usage: dict = {}
        cancelled = False
        async for chunk in self.kernel.stream_post(
            "/rpc/chat/stream",
            {"task": task.model_dump(mode="json")},
            abort_event=abort,
        ):
            if self.is_cancelled(task.task_id) or chunk.get("cancelled"):
                cancelled = True
                error = "cancelled"
                break
            if chunk.get("error") and chunk.get("done"):
                error = chunk["error"]
                if chunk.get("cancelled"):
                    cancelled = True
                if chunk.get("usage"):
                    usage = chunk["usage"]
                break
            if chunk.get("error") and not chunk.get("done"):
                error = chunk["error"]
                break
            notice = chunk.get("notice")
            if notice:
                payload = {
                    "message": notice,
                    "retry_attempt": chunk.get("retry_attempt"),
                    "retry_wait_seconds": chunk.get("retry_wait_seconds"),
                }
                if chunk.get("notice_kind"):
                    payload["kind"] = chunk.get("notice_kind")
                if chunk.get("compaction"):
                    payload["compaction"] = chunk.get("compaction")
                    # Persist ledger on session for later navigation
                    try:
                        entry = chunk["compaction"]

                        def _ledger(sess: dict) -> None:
                            from src.core_kernel.compaction_ledger import append_compaction_ledger

                            append_compaction_ledger(sess, entry)

                        await self.sessions.redis.update_session(
                            task.session_id, _ledger, preserve_messages=True
                        )
                    except Exception:
                        pass
                await self._publish(
                    task,
                    EventType.TASK_STATUS,
                    payload,
                )
                continue

            tool_call = chunk.get("tool_call")
            if tool_call:
                await self.sessions.append(
                    task.session_id,
                    ChatMessage(
                        role=ChatRole.ASSISTANT,
                        content="",
                        metadata={"tool_calls": [tool_call], "kind": "tool_call"},
                    ),
                )
                await self._publish(task, EventType.TASK_TOOL_CALL, tool_call)
                continue

            tool_result = chunk.get("tool_result")
            if tool_result:
                await self.sessions.append(
                    task.session_id,
                    ChatMessage(
                        role=ChatRole.TOOL,
                        content=str(
                            tool_result.get("result")
                            if tool_result.get("success")
                            else tool_result.get("error") or ""
                        ),
                        name=tool_result.get("name"),
                        tool_call_id=tool_result.get("id"),
                        metadata={"tool_result": tool_result, "kind": "tool_result"},
                    ),
                )
                await self._publish(task, EventType.TASK_TOOL_RESULT, tool_result)
                continue

            tool_approval = chunk.get("tool_approval")
            if tool_approval:
                await self._publish(task, EventType.TASK_TOOL_APPROVAL, tool_approval)
                continue

            ask_user = chunk.get("ask_user")
            if ask_user:
                await self._publish(task, EventType.TASK_ASK_USER, ask_user)
                continue

            plan_review = chunk.get("plan_review")
            if plan_review:
                await self._publish(task, EventType.TASK_PLAN_REVIEW, plan_review)
                continue

            plan_mode = chunk.get("plan_mode")
            if plan_mode:
                await self._publish(task, EventType.TASK_PLAN_MODE, plan_mode)
                continue

            todos = chunk.get("todos")
            if todos:
                await self._publish(task, EventType.TASK_TODOS, todos)
                continue

            canvas_open = chunk.get("canvas_open")
            if canvas_open:
                await self._publish(task, EventType.TASK_CANVAS_OPEN, canvas_open)
                continue

            subagent = chunk.get("subagent")
            if subagent:
                await self._publish(task, EventType.TASK_SUBAGENT, subagent)
                continue

            inbox_claimed = chunk.get("inbox_claimed")
            if inbox_claimed:
                items = inbox_claimed if isinstance(inbox_claimed, list) else [inbox_claimed]
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    text = str(item.get("content") or "").strip()
                    if not text:
                        continue
                    await self.sessions.append(
                        task.session_id,
                        ChatMessage(
                            role=ChatRole.USER,
                            content=text,
                            metadata={
                                "kind": "inbox_steer",
                                "inbox_id": item.get("id"),
                                "inbox_kind": "steer",
                            },
                        ),
                    )
                remaining = await self.sessions.get_inbox(task.session_id)
                await self._publish(
                    task,
                    EventType.TASK_INBOX,
                    {"action": "claimed", "items_claimed": items, "items": remaining},
                )
                continue

            reasoning_delta = chunk.get("reasoning_delta") or ""
            if reasoning_delta:
                reasoning_collected += reasoning_delta
                await self._publish(
                    task,
                    EventType.TASK_REASONING,
                    {"delta": reasoning_delta},
                )
                continue

            delta = chunk.get("delta") or ""
            if delta:
                collected += delta
                await self._publish(
                    task,
                    EventType.TASK_DELTA,
                    {"delta": delta, "content_so_far": collected},
                )
            if chunk.get("done"):
                if chunk.get("content"):
                    collected = chunk["content"]
                if chunk.get("usage"):
                    usage = chunk["usage"]
                if chunk.get("plan_ready"):
                    await self._publish(
                        task,
                        EventType.TASK_PLAN_READY,
                        {"content": collected, "session_id": task.session_id},
                    )

        if cancelled or (error == "cancelled"):
            await self._publish(
                task,
                EventType.TASK_FAILED,
                {"error": "已停止生成", "cancelled": True, "partial": collected or None},
            )
            return

        if error and not collected:
            await self._publish(task, EventType.TASK_FAILED, {"error": error, "usage": usage})
            return

        session_usage = await self.sessions.add_usage(task.session_id, usage or {})
        model_meta = {
            "usage": usage or {},
            "model_name": (task.model_name or "").strip(),
            "model_provider": (task.model_provider or "").strip(),
        }
        if reasoning_collected:
            model_meta["reasoning"] = reasoning_collected
        await self.sessions.append(
            task.session_id,
            ChatMessage(
                role=ChatRole.ASSISTANT,
                content=collected,
                metadata=model_meta,
            ),
        )
        await self._publish(
            task,
            EventType.TASK_COMPLETED,
            {
                "content": collected,
                "usage": usage or {},
                "session_usage": session_usage,
                "model_name": model_meta["model_name"],
                "model_provider": model_meta["model_provider"],
                "reasoning": reasoning_collected or None,
            },
        )
        await self._drain_queue_followup(task)

    async def _drain_queue_followup(self, parent: StandardTask) -> None:
        """After a successful turn, enqueue the next queued inbox message as a new task."""
        try:
            item = await self.sessions.claim_next_queued(parent.session_id)
        except Exception:
            logger.exception("claim queue inbox failed for %s", parent.session_id)
            return
        if not item:
            return
        remaining = await self.sessions.get_inbox(parent.session_id)
        await self._publish(
            parent,
            EventType.TASK_INBOX,
            {"action": "claimed", "items_claimed": [item], "items": remaining},
        )
        follow = StandardTask(
            task_id=new_id("task_"),
            session_id=parent.session_id,
            channel=parent.channel,
            user_id=parent.user_id,
            content=str(item.get("content") or ""),
            stream=True,
            tools_enabled=parent.tools_enabled,
            model_provider=parent.model_provider,
            model_name=parent.model_name,
            metadata={
                **(parent.metadata or {}),
                "from_inbox": item.get("id"),
                "inbox_kind": "queue",
            },
        )
        try:
            await self.queue.enqueue(follow)
        except Exception:
            logger.exception("enqueue queue-followup failed for %s", parent.session_id)
            # Best-effort restore so the user can retry
            try:
                await self.sessions.push_inbox_item(
                    parent.session_id,
                    kind="queue",
                    content=str(item.get("content") or ""),
                    source=str(item.get("source") or "user"),
                )
            except Exception:
                logger.exception("restore queue item failed")

    async def _publish(self, task: StandardTask, event_type: EventType, payload: dict) -> None:
        event = BusEvent(
            event_type=event_type,
            task_id=task.task_id,
            session_id=task.session_id,
            channel=task.channel if isinstance(task.channel, ChannelType) else ChannelType(task.channel),
            payload=payload,
        )
        try:
            wire = {
                "event_id": event.event_id,
                "event_type": event.event_type.value,
                "task_id": event.task_id,
                "session_id": event.session_id,
                "payload": event.payload,
                "ts": event.ts.isoformat() if hasattr(event.ts, "isoformat") else str(event.ts),
            }
            await self.redis.append_session_event(task.session_id, wire)
        except Exception:
            logger.exception("append_session_event failed for %s", task.session_id)
        await self.redis.publish_event(event)
