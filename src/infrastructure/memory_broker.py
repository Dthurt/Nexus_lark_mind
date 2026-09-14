"""In-memory broker for local single-process mode (no Redis / Docker)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set

import orjson

from src.common.config import Settings, get_settings
from src.common.errors import QueueError
from src.common.schemas import BusEvent, StandardTask

logger = logging.getLogger(__name__)

EventHandler = Callable[[BusEvent], Awaitable[None]]


class MemoryBroker:
    """Duck-compatible with RedisClient for queue / pubsub / session cache."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        self._queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._subscribers: Set[asyncio.Queue[bytes]] = set()
        self._sessions: Dict[str, dict] = {}
        self._session_order: List[str] = []
        self._kv: Dict[str, Any] = {}
        self._event_logs: Dict[str, List[dict]] = {}
        self._lock = asyncio.Lock()
        self._connected = False

    async def connect(self) -> None:
        already = self._connected
        self._connected = True
        if not already:
            logger.info("Memory broker ready (local mode, no Redis)")

    async def close(self) -> None:
        self._connected = False
        self._subscribers.clear()

    async def enqueue_task(self, task: StandardTask) -> None:
        if not self._connected:
            raise QueueError("Memory broker not connected")
        await self._queue.put(orjson.dumps(task.model_dump(mode="json")))

    async def dequeue_task(self, timeout: int = 5) -> Optional[StandardTask]:
        try:
            raw = await asyncio.wait_for(self._queue.get(), timeout=float(timeout))
        except asyncio.TimeoutError:
            return None
        except Exception as exc:
            raise QueueError(f"dequeue failed: {exc}") from exc
        return StandardTask.model_validate(orjson.loads(raw))

    async def publish_event(self, event: BusEvent) -> None:
        payload = orjson.dumps(event.model_dump(mode="json"))
        dead: List[asyncio.Queue[bytes]] = []
        for q in list(self._subscribers):
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                dead.append(q)
        for q in dead:
            self._subscribers.discard(q)

    async def subscribe_events(
        self,
        handler: EventHandler,
        stop_event: Optional[asyncio.Event] = None,
    ) -> None:
        q: asyncio.Queue[bytes] = asyncio.Queue(maxsize=1024)
        self._subscribers.add(q)
        logger.debug("Memory broker subscriber attached (%s total)", len(self._subscribers))
        try:
            while True:
                if stop_event and stop_event.is_set():
                    break
                try:
                    raw = await asyncio.wait_for(q.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                try:
                    event = BusEvent.model_validate(orjson.loads(raw))
                    await handler(event)
                except Exception:
                    logger.exception("Failed to handle memory bus event")
        finally:
            self._subscribers.discard(q)

    def _session_key(self, session_id: str) -> str:
        return f"{self.settings.redis_session_prefix}{session_id}"

    async def set_session(self, session_id: str, payload: dict, ttl: int = 86400) -> None:
        key = self._session_key(session_id)
        self._sessions[key] = payload
        if session_id not in self._session_order:
            self._session_order.append(session_id)

    async def get_session(self, session_id: str) -> Optional[dict]:
        return self._sessions.get(self._session_key(session_id))

    async def delete_session(self, session_id: str) -> None:
        self._sessions.pop(self._session_key(session_id), None)
        self._session_order = [s for s in self._session_order if s != session_id]

    async def list_sessions(self) -> List[dict]:
        out: List[dict] = []
        for sid in reversed(self._session_order):
            sess = await self.get_session(sid)
            if not sess:
                continue
            msgs = sess.get("messages") or []
            preview = ""
            for m in reversed(msgs):
                if m.get("role") == "user" and m.get("content"):
                    preview = str(m["content"])[:80]
                    break
            out.append(
                {
                    "session_id": sid,
                    "title": sess.get("title") or "新对话",
                    "updated_at": sess.get("updated_at"),
                    "created_at": sess.get("created_at"),
                    "message_count": len(msgs),
                    "preview": preview,
                    "channel": sess.get("channel"),
                    "cwd": sess.get("cwd") or "",
                    "workspace_id": sess.get("workspace_id") or "",
                    "workspace_title": sess.get("workspace_title") or "",
                    "workspace_kind": sess.get("workspace_kind") or "local",
                    "ssh_host_id": sess.get("ssh_host_id") or "",
                }
            )
        return out

    async def append_session_message(self, session_id: str, message: dict, ttl: int = 86400) -> dict:
        session = await self.get_session(session_id)
        if session is None:
            raise KeyError(f"session missing for append: {session_id}")
        session.setdefault("messages", []).append(message)
        await self.set_session(session_id, session, ttl=ttl)
        return session

    # ----- Generic KV + SSE event ring (Wave C) -----

    async def kv_set(self, key: str, value: dict, ttl: int = 86400) -> None:
        self._kv[key] = dict(value)

    async def kv_get(self, key: str) -> Optional[dict]:
        raw = self._kv.get(key)
        return dict(raw) if isinstance(raw, dict) else None

    async def kv_delete(self, key: str) -> None:
        self._kv.pop(key, None)

    async def append_session_event(
        self,
        session_id: str,
        event: dict,
        *,
        maxlen: int = 300,
    ) -> None:
        log = self._event_logs.setdefault(session_id, [])
        log.append(dict(event))
        if len(log) > maxlen:
            del log[: len(log) - maxlen]

    async def list_session_events_after(
        self,
        session_id: str,
        after_event_id: str = "",
    ) -> List[dict]:
        log = list(self._event_logs.get(session_id) or [])
        if not after_event_id:
            return log
        out: List[dict] = []
        seen = False
        for ev in log:
            eid = str(ev.get("event_id") or "")
            if not seen:
                if eid == after_event_id:
                    seen = True
                continue
            out.append(ev)
        # If after_id not found, return full log (client may have stale cursor)
        return out if seen else log


_SHARED: Optional[MemoryBroker] = None


def get_shared_memory_broker(settings: Optional[Settings] = None) -> MemoryBroker:
    global _SHARED
    if _SHARED is None:
        _SHARED = MemoryBroker(settings or get_settings())
    return _SHARED
