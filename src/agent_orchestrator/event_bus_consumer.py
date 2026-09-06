"""Optional side-consumer for orchestrator-level event observation / metrics."""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, Optional

from src.common.schemas import BusEvent
from src.infrastructure.redis_client import RedisClient

logger = logging.getLogger(__name__)

EventHandler = Callable[[BusEvent], Awaitable[None]]


class EventBusConsumer:
    def __init__(self, redis_client: RedisClient) -> None:
        self.redis = redis_client
        self._stop = asyncio.Event()
        self._handlers: list[EventHandler] = []

    def add_handler(self, handler: EventHandler) -> None:
        self._handlers.append(handler)

    async def start(self) -> None:
        self._stop.clear()

        async def _handle(event: BusEvent) -> None:
            logger.debug(
                "bus event %s task=%s channel=%s",
                event.event_type,
                event.task_id,
                event.channel,
            )
            for handler in self._handlers:
                try:
                    await handler(event)
                except Exception:
                    logger.exception("event handler failed")

        await self.redis.subscribe_events(_handle, stop_event=self._stop)

    def stop(self) -> None:
        self._stop.set()
