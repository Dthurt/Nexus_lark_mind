"""Global Redis client — queue, pub/sub event bus, session cache."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncIterator, Awaitable, Callable, Optional, Union

import orjson
import redis.asyncio as redis

from src.common.config import Settings, get_settings
from src.common.errors import QueueError
from src.common.schemas import BusEvent, StandardTask

logger = logging.getLogger(__name__)

Broker = Any  # RedisClient | MemoryBroker


def create_broker(settings: Optional[Settings] = None) -> Broker:
    """Factory: memory:// → in-process broker; otherwise Redis."""
    settings = settings or get_settings()
    url = (settings.redis_url or "").strip().lower()
    if url.startswith("memory:"):
        from src.infrastructure.memory_broker import get_shared_memory_broker

        return get_shared_memory_broker(settings)
    return RedisClient(settings)


class RedisClient:
    """Singleton-style wrapper; construct once per process."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        self._redis: Optional[redis.Redis] = None
        self._pubsub: Optional[redis.client.PubSub] = None

    async def connect(self) -> None:
        if self._redis is not None:
            return
        self._redis = redis.from_url(
            self.settings.redis_url,
            encoding="utf-8",
            decode_responses=False,
        )
        await self._redis.ping()
        logger.info("Redis connected: %s", self.settings.redis_url)

    async def close(self) -> None:
        if self._pubsub is not None:
            await self._pubsub.close()
            self._pubsub = None
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None

    @property
    def r(self) -> redis.Redis:
        if self._redis is None:
            raise QueueError("Redis not connected")
        return self._redis

    # ----- Task queue (LPUSH / BRPOP) -----

    async def enqueue_task(self, task: StandardTask) -> None:
        try:
            await self.r.lpush(
                self.settings.redis_task_queue,
                orjson.dumps(task.model_dump(mode="json")),
            )
        except Exception as exc:
            raise QueueError(f"enqueue failed: {exc}") from exc

    async def dequeue_task(self, timeout: int = 5) -> Optional[StandardTask]:
        try:
            item = await self.r.brpop(self.settings.redis_task_queue, timeout=timeout)
        except Exception as exc:
            raise QueueError(f"dequeue failed: {exc}") from exc
        if not item:
            return None
        _, raw = item
        return StandardTask.model_validate(orjson.loads(raw))

    # ----- Event bus (PUB/SUB) -----

    async def publish_event(self, event: BusEvent) -> None:
        try:
            await self.r.publish(
                self.settings.redis_event_channel,
                orjson.dumps(event.model_dump(mode="json")),
            )
        except Exception as exc:
            raise QueueError(f"publish failed: {exc}") from exc

    async def subscribe_events(
        self,
        handler: Callable[[BusEvent], Awaitable[None]],
        stop_event: Optional[asyncio.Event] = None,
    ) -> None:
        pubsub = self.r.pubsub()
        await pubsub.subscribe(self.settings.redis_event_channel)
        self._pubsub = pubsub
        logger.info("Subscribed to event channel %s", self.settings.redis_event_channel)
        try:
            while True:
                if stop_event and stop_event.is_set():
                    break
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0,
                )
                if message is None:
                    await asyncio.sleep(0.05)
                    continue
                data = message.get("data")
                if not data:
                    continue
                try:
                    event = BusEvent.model_validate(orjson.loads(data))
                    await handler(event)
                except Exception:
                    logger.exception("Failed to handle bus event")
        finally:
            await pubsub.unsubscribe(self.settings.redis_event_channel)
            await pubsub.close()

    async def iter_events(self) -> AsyncIterator[BusEvent]:
        pubsub = self.r.pubsub()
        await pubsub.subscribe(self.settings.redis_event_channel)
        try:
            while True:
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0,
                )
                if message is None:
                    await asyncio.sleep(0.05)
                    continue
                data = message.get("data")
                if not data:
                    continue
                yield BusEvent.model_validate(orjson.loads(data))
        finally:
            await pubsub.unsubscribe(self.settings.redis_event_channel)
            await pubsub.close()

    # ----- Session cache -----

    def _session_key(self, session_id: str) -> str:
        return f"{self.settings.redis_session_prefix}{session_id}"

    async def set_session(self, session_id: str, payload: dict, ttl: int = 86400) -> None:
        await self.r.set(
            self._session_key(session_id),
            orjson.dumps(payload),
            ex=ttl,
        )

    async def get_session(self, session_id: str) -> Optional[dict]:
        raw = await self.r.get(self._session_key(session_id))
        if not raw:
            return None
        return orjson.loads(raw)

    async def append_session_message(self, session_id: str, message: dict, ttl: int = 86400) -> dict:
        session = await self.get_session(session_id) or {
            "session_id": session_id,
            "messages": [],
        }
        session.setdefault("messages", []).append(message)
        await self.set_session(session_id, session, ttl=ttl)
        return session
