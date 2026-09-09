"""Plugin lifecycle states and base protocol."""

from __future__ import annotations

import abc
import enum
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class PluginState(str, enum.Enum):
    INIT = "init"
    READY = "ready"
    DISABLED = "disabled"
    ERROR = "error"
    TEARDOWN = "teardown"


class PluginManifest(BaseModel):
    plugin_id: str
    name: str
    kind: str  # mcp_stdio | mcp_http | cli
    version: str = "1.0.0"
    description: str = ""
    enabled: bool = True
    tools: List[Dict[str, Any]] = Field(default_factory=list)
    config: Dict[str, Any] = Field(default_factory=dict)


class BasePlugin(abc.ABC):
    def __init__(self, manifest: PluginManifest) -> None:
        self.manifest = manifest
        self.state = PluginState.INIT
        self.last_error: Optional[str] = None
        self.last_teardown_at: Optional[datetime] = None
        self.last_ready_at: Optional[datetime] = None

    @property
    def plugin_id(self) -> str:
        return self.manifest.plugin_id

    def health_summary(self) -> Dict[str, Any]:
        status = "ok" if self.state == PluginState.READY else self.state.value
        return {
            "status": status,
            "state": self.state.value,
            "last_error": self.last_error,
            "last_ready_at": self.last_ready_at.isoformat() if self.last_ready_at else None,
            "last_teardown_at": self.last_teardown_at.isoformat() if self.last_teardown_at else None,
        }

    async def init(self) -> None:
        self.state = PluginState.INIT
        await self._on_init()

    async def ready(self) -> None:
        await self._on_ready()
        self.state = PluginState.READY
        self.last_error = None
        self.last_ready_at = datetime.now(timezone.utc)

    async def disable(self) -> None:
        """Stop runtime resources, then mark DISABLED (keeps plugin registered)."""
        try:
            await self._on_teardown()
            self.last_teardown_at = datetime.now(timezone.utc)
            logger.info("Plugin %s torn down on disable", self.plugin_id)
        except Exception as exc:
            self.last_error = str(exc)
            logger.exception("Plugin %s teardown failed on disable", self.plugin_id)
        self.state = PluginState.DISABLED

    async def enable(self) -> None:
        if self.state in (PluginState.TEARDOWN, PluginState.DISABLED, PluginState.ERROR, PluginState.INIT):
            await self.init()
        await self.ready()

    async def teardown(self) -> None:
        await self._on_teardown()
        self.last_teardown_at = datetime.now(timezone.utc)
        self.state = PluginState.TEARDOWN
        logger.info("Plugin %s teardown complete", self.plugin_id)

    async def invoke(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        if self.state != PluginState.READY:
            raise RuntimeError(f"plugin {self.plugin_id} not ready (state={self.state})")
        return await self._on_invoke(tool_name, arguments)

    @abc.abstractmethod
    async def _on_init(self) -> None:
        ...

    @abc.abstractmethod
    async def _on_ready(self) -> None:
        ...

    @abc.abstractmethod
    async def _on_invoke(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        ...

    @abc.abstractmethod
    async def _on_teardown(self) -> None:
        ...
