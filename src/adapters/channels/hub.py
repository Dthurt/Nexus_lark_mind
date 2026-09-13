"""Unified channel hub — register IM adapters and fan-out bus events."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional, Protocol

from src.common.schemas import BusEvent, ChannelType

logger = logging.getLogger(__name__)


class BusAware(Protocol):
    channel: ChannelType

    async def on_bus_event(self, event: BusEvent) -> None: ...


class ChannelHub:
    """Thin registry so adapters share one bus subscription path."""

    def __init__(self) -> None:
        self._adapters: Dict[str, BusAware] = {}
        self._restarts: Dict[str, Callable[[], Awaitable[Dict[str, Any]]]] = {}

    def register(self, adapter: BusAware, *, restart: Optional[Callable[[], Awaitable[Dict[str, Any]]]] = None) -> None:
        key = adapter.channel.value if hasattr(adapter.channel, "value") else str(adapter.channel)
        self._adapters[key] = adapter
        if restart is not None:
            self._restarts[key] = restart

    def get(self, channel: str) -> Optional[BusAware]:
        return self._adapters.get(channel)

    def channels(self) -> List[str]:
        return list(self._adapters.keys())

    async def dispatch_bus(self, event: BusEvent) -> None:
        for key, adapter in list(self._adapters.items()):
            try:
                await adapter.on_bus_event(event)
            except Exception:
                logger.exception("Channel hub bus dispatch failed channel=%s", key)

    async def restart(self, channel: str) -> Dict[str, Any]:
        fn = self._restarts.get(channel)
        if fn is None:
            return {"ok": False, "message": f"no restart handler for {channel}"}
        return await fn()

    def runtime_status(self) -> Dict[str, Any]:
        return {
            "registered": self.channels(),
            "restartable": list(self._restarts.keys()),
        }
