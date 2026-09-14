"""Global Redis client — queue, pub/sub event bus, session cache."""

from __future__ import annotations

import asyncio
import logging
import time
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
            health_check_interval=30,
            socket_keepalive=True,
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
        # Wall-clock score — comparable across orchestrator + kernel processes.
        await self.r.zadd(self.settings.redis_session_prefix + "index", {session_id: time.time()})

    async def get_session(self, session_id: str) -> Optional[dict]:
        raw = await self.r.get(self._session_key(session_id))
        if not raw:
            return None
        return orjson.loads(raw)

    async def delete_session(self, session_id: str) -> None:
        await self.r.delete(self._session_key(session_id))
        await self.r.zrem(self.settings.redis_session_prefix + "index", session_id)

    async def list_sessions(self) -> list:
        index_key = self.settings.redis_session_prefix + "index"
        ids = await self.r.zrevrange(index_key, 0, 99)
        out = []
        for sid in ids:
            session_id = sid.decode() if isinstance(sid, (bytes, bytearray)) else sid
            sess = await self.get_session(session_id)
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
                    "session_id": session_id,
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
        """Append a message with optimistic locking. Never invents an empty session."""
        key = self._session_key(session_id)
        index = self.settings.redis_session_prefix + "index"
        last_err: Optional[Exception] = None
        for _ in range(8):
            try:
                async with self.r.pipeline(transaction=True) as pipe:
                    await pipe.watch(key)
                    raw = await self.r.get(key)
                    if not raw:
                        await pipe.unwatch()
                        raise QueueError(f"session missing for append: {session_id}")
                    session = orjson.loads(raw)
                    if not isinstance(session, dict):
                        await pipe.unwatch()
                        raise QueueError(f"session corrupt for append: {session_id}")
                    session.setdefault("messages", []).append(message)
                    pipe.multi()
                    pipe.set(key, orjson.dumps(session), ex=ttl)
                    pipe.zadd(index, {session_id: time.time()})
                    await pipe.execute()
                    return session
            except redis.WatchError as exc:
                last_err = exc
                continue
        raise QueueError(f"append_session_message conflict: {session_id}") from last_err

    # ----- Generic KV + SSE event ring (Wave C) -----

    def _kv_key(self, key: str) -> str:
        return f"{self.settings.redis_session_prefix}kv:{key}"

    def _events_key(self, session_id: str) -> str:
        return f"{self.settings.redis_session_prefix}events:{session_id}"

    async def kv_set(self, key: str, value: dict, ttl: int = 86400) -> None:
        await self.r.set(self._kv_key(key), orjson.dumps(value), ex=ttl)

    async def kv_get(self, key: str) -> Optional[dict]:
        raw = await self.r.get(self._kv_key(key))
        if not raw:
            return None
        return orjson.loads(raw)

    async def kv_delete(self, key: str) -> None:
        await self.r.delete(self._kv_key(key))

    async def append_session_event(
        self,
        session_id: str,
        event: dict,
        *,
        maxlen: int = 300,
    ) -> None:
        key = self._events_key(session_id)
        await self.r.rpush(key, orjson.dumps(event))
        await self.r.ltrim(key, -int(maxlen), -1)
        await self.r.expire(key, 86400)

    async def list_session_events_after(
        self,
        session_id: str,
        after_event_id: str = "",
    ) -> list:
        key = self._events_key(session_id)
        raw_list = await self.r.lrange(key, 0, -1)
        log = [orjson.loads(x) for x in raw_list or []]
        if not after_event_id:
            return log
        out = []
        seen = False
        for ev in log:
            eid = str(ev.get("event_id") or "")
            if not seen:
                if eid == after_event_id:
                    seen = True
                continue
            out.append(ev)
        return out if seen else log
