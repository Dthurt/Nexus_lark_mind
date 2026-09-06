"""Task dispatcher — consumes queue, calls kernel RPC, publishes stream events."""

from __future__ import annotations

import logging
from typing import Optional

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

    async def dispatch(self, task: StandardTask) -> None:
        task.status = TaskStatus.RUNNING
        await self.sessions.ensure(
            task.session_id,
            user_id=task.user_id,
            channel=task.channel.value,
        )

        history = await self.sessions.load_messages(task.session_id)
        messages = [
            ChatMessage(role=ChatRole(m["role"]), content=m["content"])
            for m in history
            if m.get("role") in {"system", "user", "assistant", "tool"}
        ]
        messages.append(ChatMessage(role=ChatRole.USER, content=task.content))
        task.messages = messages

        await self._publish(task, EventType.TASK_STARTED, {})
        await self.sessions.append(task.session_id, ChatMessage(role=ChatRole.USER, content=task.content))

        if task.stream:
            await self._dispatch_stream(task)
        else:
            await self._dispatch_complete(task)

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

    async def _dispatch_stream(self, task: StandardTask) -> None:
        collected = ""
        error: Optional[str] = None
        async for chunk in self.kernel.stream_post(
            "/rpc/chat/stream",
            {"task": task.model_dump(mode="json")},
        ):
            if chunk.get("error"):
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
            delta = chunk.get("delta") or ""
            if delta:
                collected += delta
                await self._publish(
                    task,
                    EventType.TASK_DELTA,
                    {"delta": delta, "content_so_far": collected},
                )
            if chunk.get("done") and chunk.get("content"):
                collected = chunk["content"]

        if error:
            await self._publish(task, EventType.TASK_FAILED, {"error": error})
            return

        await self.sessions.append(
            task.session_id,
            ChatMessage(role=ChatRole.ASSISTANT, content=collected),
        )
        await self._publish(
            task,
            EventType.TASK_COMPLETED,
            {"content": collected},
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
