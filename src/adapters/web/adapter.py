"""Web chat adapter — enqueue tasks and expose per-session SSE streams."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncIterator, Dict, Optional, Set

import orjson

from src.adapters.base_adapter import BaseAdapter
from src.common.config import Settings, get_settings
from src.common.rpc_client import RpcClient
from src.common.schemas import BusEvent, ChannelType, EventType, StandardTask, new_id
from src.infrastructure.redis_client import RedisClient

logger = logging.getLogger(__name__)


class WebAdapter(BaseAdapter):
    channel = ChannelType.WEB

    def __init__(
        self,
        orchestrator: RpcClient,
        redis_client: RedisClient,
        settings: Optional[Settings] = None,
    ) -> None:
        super().__init__(orchestrator, redis_client)
        self.settings = settings or get_settings()
        # session_id -> set of asyncio.Queue
        self._subscribers: Dict[str, Set[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()

    async def handle_inbound(self, payload: Dict[str, Any]) -> Optional[StandardTask]:
        content = (payload.get("content") or "").strip()
        if not content:
            return None
        session_id = payload.get("session_id") or new_id("web_")
        user_id = payload.get("user_id") or "web-user"
        meta: Dict[str, Any] = {"source": "web"}
        cwd = (payload.get("cwd") or "").strip()
        workspace_id = (payload.get("workspace_id") or "").strip()
        workspace_title = (payload.get("workspace_title") or "").strip()
        workspace_kind = (payload.get("workspace_kind") or "").strip()
        ssh_host_id = (payload.get("ssh_host_id") or "").strip()
        if workspace_id and not cwd:
            try:
                from src.adapters.workspaces import get_workspace_store

                rec = get_workspace_store().get(workspace_id)
                if rec:
                    cwd = rec.path
                    workspace_title = workspace_title or rec.title
                    workspace_kind = workspace_kind or rec.kind or "local"
                    ssh_host_id = ssh_host_id or rec.ssh_host_id or ""
            except Exception:
                logger.exception("Failed resolving workspace_id=%s", workspace_id)
        if cwd:
            meta["cwd"] = cwd
            meta["workspace_id"] = workspace_id
            meta["workspace_title"] = workspace_title
            meta["workspace_kind"] = workspace_kind or ("ssh" if ssh_host_id else "local")
            meta["ssh_host_id"] = ssh_host_id
        if payload.get("agent_mode") is not None:
            meta["agent_mode"] = str(payload.get("agent_mode") or "agent").strip().lower()
        if payload.get("auto_accept") is not None:
            meta["auto_accept"] = bool(payload.get("auto_accept"))
        task = StandardTask(
            session_id=session_id,
            channel=ChannelType.WEB,
            user_id=user_id,
            content=content,
            model_provider=payload.get("model_provider"),
            model_name=payload.get("model_name"),
            stream=bool(payload.get("stream", True)),
            tools_enabled=bool(payload.get("tools_enabled", True)),
            metadata=meta,
        )
        await self.submit(task)
        return task

    async def subscribe(self, session_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=256)
        async with self._lock:
            self._subscribers.setdefault(session_id, set()).add(queue)
        return queue

    async def unsubscribe(self, session_id: str, queue: asyncio.Queue) -> None:
        async with self._lock:
            subs = self._subscribers.get(session_id)
            if not subs:
                return
            subs.discard(queue)
            if not subs:
                self._subscribers.pop(session_id, None)

    async def on_bus_event(self, event: BusEvent) -> None:
        if event.channel != ChannelType.WEB:
            return
        async with self._lock:
            subs = list(self._subscribers.get(event.session_id, set()))
        payload = {
            "event_type": event.event_type.value,
            "task_id": event.task_id,
            "session_id": event.session_id,
            "payload": event.payload,
            "ts": event.ts.isoformat(),
        }
        for q in subs:
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                logger.warning("SSE queue full for session %s", event.session_id)

    async def sse_stream(self, session_id: str) -> AsyncIterator[bytes]:
        queue = await self.subscribe(session_id)
        try:
            yield b"data: " + orjson.dumps({"event_type": "session.ready", "session_id": session_id}) + b"\n\n"
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    yield b": keepalive\n\n"
                    continue
                yield b"data: " + orjson.dumps(item) + b"\n\n"
                if item.get("event_type") in {
                    EventType.TASK_COMPLETED.value,
                    EventType.TASK_FAILED.value,
                }:
                    # keep connection for multi-turn; do not close
                    continue
        finally:
            await self.unsubscribe(session_id, queue)
