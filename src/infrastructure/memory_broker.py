"""In-memory broker for local single-process mode (no Redis / Docker)."""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, Dict, List, Optional, Set

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
        self._lock = asyncio.Lock()
        self._connected = False

    async def connect(self) -> None:
        self._connected = True
        logger.info("Memory broker connected (local mode, no Redis)")

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
        logger.info("Memory broker subscribed to events")
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
        self._sessions[self._session_key(session_id)] = payload

    async def get_session(self, session_id: str) -> Optional[dict]:
        return self._sessions.get(self._session_key(session_id))

    async def append_session_message(self, session_id: str, message: dict, ttl: int = 86400) -> dict:
        session = await self.get_session(session_id) or {
            "session_id": session_id,
            "messages": [],
        }
        session.setdefault("messages", []).append(message)
        await self.set_session(session_id, session, ttl=ttl)
        return session


_SHARED: Optional[MemoryBroker] = None


def get_shared_memory_broker(settings: Optional[Settings] = None) -> MemoryBroker:
    global _SHARED
    if _SHARED is None:
        _SHARED = MemoryBroker(settings or get_settings())
    return _SHARED
