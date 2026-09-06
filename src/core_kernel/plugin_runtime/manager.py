"""Plugin manager — hot plug, isolation, crash self-heal, CLI auto-register."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.common.config import Settings, get_settings
from src.common.errors import NotFoundError, PluginError, PluginIsolatedCrash
from src.common.schemas import PluginInvokeRequest, PluginInvokeResult
from src.core_kernel.plugin_runtime.cli_wrapper import CliPlugin
from src.core_kernel.plugin_runtime.lifecycle import BasePlugin, PluginManifest, PluginState
from src.core_kernel.plugin_runtime.mcp_http import McpHttpPlugin
from src.core_kernel.plugin_runtime.mcp_stdio import McpStdioPlugin
from src.infrastructure.storage.repositories import PluginCallRepository

logger = logging.getLogger(__name__)


class PluginManager:
    def __init__(
        self,
        settings: Optional[Settings] = None,
        session_factory: Optional[async_sessionmaker[AsyncSession]] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.session_factory = session_factory
        self.plugins: Dict[str, BasePlugin] = {}
        self._lock = asyncio.Lock()

    async def bootstrap(self) -> None:
        root = Path(self.settings.plugins_dir)
        root.mkdir(parents=True, exist_ok=True)
        (root / "mcp").mkdir(exist_ok=True)
        (root / "cli").mkdir(exist_ok=True)

        # Load MCP manifests
        for manifest_path in sorted((root / "mcp").glob("*.json")):
            try:
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest = PluginManifest.model_validate(data)
                await self.load(manifest)
            except Exception:
                logger.exception("Failed loading MCP manifest %s", manifest_path)

        if self.settings.cli_auto_register:
            await self.scan_cli_directory(root / "cli")

        # Built-in echo tool for zero-config demos
        if "builtin.echo" not in self.plugins:
            await self.load(_InProcessEchoManifest())

    async def scan_cli_directory(self, cli_dir: Path) -> None:
        if not cli_dir.exists():
            return
        for path in sorted(cli_dir.iterdir()):
            if path.name.startswith("."):
                continue
            if path.suffix.lower() not in {".py", ".sh", ".js", ".ps1", ".bat", ".cmd"} and not path.is_file():
                continue
            if not path.is_file():
                continue
            plugin_id = f"cli.{path.stem}"
            if plugin_id in self.plugins:
                continue
            script: str
            if path.suffix.lower() == ".py":
                script = str(path.resolve())
                # Prefer explicit python invocation for portability
                config = {
                    "script": "python",
                    "tool_name": path.stem,
                    "input_mode": "stdin_json",
                    "timeout": 60,
                    "_args_prefix": [script],
                }
            else:
                config = {
                    "script": str(path.resolve()),
                    "tool_name": path.stem,
                    "input_mode": "stdin_json",
                }
            manifest = PluginManifest(
                plugin_id=plugin_id,
                name=path.stem,
                kind="cli",
                description=f"Auto-registered CLI tool from {path.name}",
                config=config,
            )
            await self.load(manifest)

    async def load(self, manifest: PluginManifest) -> PluginManifest:
        async with self._lock:
            if manifest.plugin_id in self.plugins:
                await self.unload(manifest.plugin_id)
            plugin = self._create(manifest)
            try:
                await plugin.init()
                if manifest.enabled:
                    await plugin.ready()
                else:
                    await plugin.disable()
            except Exception as exc:
                plugin.state = PluginState.ERROR
                plugin.last_error = str(exc)
                logger.exception("Plugin %s failed to load", manifest.plugin_id)
            self.plugins[manifest.plugin_id] = plugin
            return plugin.manifest

    def _create(self, manifest: PluginManifest) -> BasePlugin:
        if manifest.kind == "mcp_stdio":
            return McpStdioPlugin(manifest)
        if manifest.kind == "mcp_http":
            return McpHttpPlugin(manifest)
        if manifest.kind == "cli":
            return CliPlugin(manifest)
        if manifest.kind == "inprocess":
            return InProcessEchoPlugin(manifest)
        raise PluginError(f"unknown plugin kind: {manifest.kind}")

    async def unload(self, plugin_id: str) -> None:
        plugin = self.plugins.pop(plugin_id, None)
        if plugin:
            try:
                await plugin.teardown()
            except Exception:
                logger.exception("Teardown failed for %s", plugin_id)

    async def enable(self, plugin_id: str) -> None:
        plugin = self._require(plugin_id)
        await plugin.enable()

    async def disable(self, plugin_id: str) -> None:
        plugin = self._require(plugin_id)
        await plugin.disable()

    def list_plugins(self) -> List[Dict[str, Any]]:
        out = []
        for p in self.plugins.values():
            out.append(
                {
                    "plugin_id": p.plugin_id,
                    "name": p.manifest.name,
                    "kind": p.manifest.kind,
                    "state": p.state.value,
                    "enabled": p.state == PluginState.READY,
                    "tools": p.manifest.tools,
                    "last_error": p.last_error,
                }
            )
        return out

    def list_tools(self) -> List[Dict[str, Any]]:
        tools: List[Dict[str, Any]] = []
        for p in self.plugins.values():
            if p.state != PluginState.READY:
                continue
            for tool in p.manifest.tools:
                item = dict(tool)
                item["plugin_id"] = p.plugin_id
                tools.append(item)
        return tools

    async def invoke(self, req: PluginInvokeRequest, *, task_id: Optional[str] = None) -> PluginInvokeResult:
        plugin = self._require(req.plugin_id)
        started = time.perf_counter()
        success = True
        error: Optional[str] = None
        result: Any = None
        try:
            if self.settings.plugin_isolation:
                result = await self._isolated_invoke(plugin, req.tool_name, req.arguments, req.timeout_seconds)
            else:
                result = await asyncio.wait_for(
                    plugin.invoke(req.tool_name, req.arguments),
                    timeout=req.timeout_seconds,
                )
        except Exception as exc:
            success = False
            error = str(exc)
            plugin.state = PluginState.ERROR
            plugin.last_error = error
            # Crash self-heal: attempt re-init in background
            asyncio.create_task(self._heal(plugin.plugin_id))
            if self.settings.plugin_isolation:
                # Isolated failure — do not crash kernel
                result = None
            else:
                raise PluginIsolatedCrash(error) from exc
        duration = (time.perf_counter() - started) * 1000
        await self._audit(req, success, result, error, duration, task_id)
        return PluginInvokeResult(
            plugin_id=req.plugin_id,
            tool_name=req.tool_name,
            success=success,
            result=result,
            error=error,
            duration_ms=duration,
        )

    async def _isolated_invoke(
        self,
        plugin: BasePlugin,
        tool_name: str,
        arguments: Dict[str, Any],
        timeout: float,
    ) -> Any:
        try:
            return await asyncio.wait_for(plugin.invoke(tool_name, arguments), timeout=timeout)
        except Exception as exc:
            raise PluginIsolatedCrash(f"{plugin.plugin_id} crashed: {exc}") from exc

    async def _heal(self, plugin_id: str) -> None:
        await asyncio.sleep(1.0)
        plugin = self.plugins.get(plugin_id)
        if not plugin:
            return
        try:
            await plugin.teardown()
            await plugin.init()
            await plugin.ready()
            logger.info("Plugin %s self-healed", plugin_id)
        except Exception:
            logger.exception("Plugin %s heal failed", plugin_id)

    def _require(self, plugin_id: str) -> BasePlugin:
        plugin = self.plugins.get(plugin_id)
        if not plugin:
            raise NotFoundError(f"plugin not found: {plugin_id}")
        return plugin

    async def _audit(
        self,
        req: PluginInvokeRequest,
        success: bool,
        result: Any,
        error: Optional[str],
        duration_ms: float,
        task_id: Optional[str],
    ) -> None:
        if self.session_factory is None:
            return
        async with self.session_factory() as session:
            repo = PluginCallRepository(session)
            await repo.record(
                plugin_id=req.plugin_id,
                tool_name=req.tool_name,
                arguments=req.arguments,
                success=success,
                result=result,
                error=error,
                duration_ms=duration_ms,
                task_id=task_id,
            )
            await session.commit()


class InProcessEchoPlugin(BasePlugin):
    async def _on_init(self) -> None:
        return None

    async def _on_ready(self) -> None:
        self.manifest.tools = [
            {
                "name": "echo",
                "description": "Echo arguments back",
                "inputSchema": {"type": "object"},
            }
        ]

    async def _on_invoke(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        return {"echo": arguments, "tool": tool_name}

    async def _on_teardown(self) -> None:
        return None


def _InProcessEchoManifest() -> PluginManifest:
    return PluginManifest(
        plugin_id="builtin.echo",
        name="Echo",
        kind="inprocess",
        description="In-process echo tool",
    )
