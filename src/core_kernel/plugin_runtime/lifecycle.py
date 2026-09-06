"""Plugin lifecycle states and base protocol."""

from __future__ import annotations

import abc
import enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


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

    @property
    def plugin_id(self) -> str:
        return self.manifest.plugin_id

    async def init(self) -> None:
        self.state = PluginState.INIT
        await self._on_init()

    async def ready(self) -> None:
        await self._on_ready()
        self.state = PluginState.READY
        self.last_error = None

    async def disable(self) -> None:
        self.state = PluginState.DISABLED

    async def enable(self) -> None:
        if self.state == PluginState.TEARDOWN:
            await self.init()
        await self.ready()

    async def teardown(self) -> None:
        await self._on_teardown()
        self.state = PluginState.TEARDOWN

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
