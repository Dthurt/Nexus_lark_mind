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
            except Exception:
                logger.exception("Dispatch failed for task %s", task.task_id)
                await self._publish(
                    task,
                    EventType.TASK_FAILED,
                    {"error": "dispatch failure"},
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
        task.metadata = {
            **(task.metadata or {}),
            "agent_mode": str(agent_mode).strip().lower() if agent_mode else "agent",
            "auto_accept": bool(auto_accept),
            "plan_status": session.get("plan_status") or "idle",
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
                await self._publish(
                    task,
                    EventType.TASK_STATUS,
                    {
                        "message": notice,
                        "retry_attempt": chunk.get("retry_attempt"),
                        "retry_wait_seconds": chunk.get("retry_wait_seconds"),
                    },
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

            subagent = chunk.get("subagent")
            if subagent:
                await self._publish(task, EventType.TASK_SUBAGENT, subagent)
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
        await self.sessions.append(
            task.session_id,
            ChatMessage(
                role=ChatRole.ASSISTANT,
                content=collected,
                metadata={"usage": usage or {}},
            ),
        )
        await self._publish(
            task,
            EventType.TASK_COMPLETED,
            {
                "content": collected,
                "usage": usage or {},
                "session_usage": session_usage,
            },
        )

    async def _publish(self, task: StandardTask, event_type: EventType, payload: dict) -> None:
        event = BusEvent(
            event_type=event_type,
            task_id=task.task_id,
            session_id=task.session_id,
            channel=task.channel if isinstance(task.channel, ChannelType) else ChannelType(task.channel),
            payload=payload,
        )
        await self.redis.publish_event(event)
