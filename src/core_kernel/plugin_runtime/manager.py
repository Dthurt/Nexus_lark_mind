"""Plugin manager — hot plug, isolation, crash self-heal, CLI auto-register."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
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
from src.core_kernel.plugin_runtime.workspace_tools import WorkspaceToolsPlugin, workspace_tools_manifest
from src.core_kernel.plugin_runtime.subagent_tools import SubagentToolsPlugin, subagent_tools_manifest
from src.core_kernel.plugin_runtime.knowledge_tools import KnowledgeToolsPlugin, knowledge_tools_manifest
from src.core_kernel.plugin_runtime.image_gen import ImageGenPlugin, image_gen_manifest
from src.core_kernel.plugin_runtime.plugin_config_store import (
    PLUGIN_CONFIG_SCHEMAS,
    get_plugin_config_store,
)
from src.infrastructure.storage.repositories import PluginCallRepository

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
PREFS_PATH = _REPO_ROOT / "data" / "plugin_prefs.json"


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
        self._prefs: Dict[str, bool] = {}
        self._inflight_invokes = 0

    @staticmethod
    def openai_tool_name(plugin_id: str, tool_name: str) -> str:
        # Coding-agent models match DSH-style short names; keep prefixed names for other plugins.
        if plugin_id in {"builtin.workspace", "builtin.subagent", "builtin.knowledge", "builtin.image_gen"}:
            return tool_name
        # Well-known CLI search tools: short names reduce "cli.web_search" prose hallucinations.
        if plugin_id.startswith("cli.") and tool_name in {
            "web_search",
            "literature_search",
            "image_search",
            "web_crawl",
            "weknora_search",
        }:
            return tool_name
        return f"{plugin_id}.{tool_name}".replace(".", "_")

    def _prefs_path(self) -> Path:
        return PREFS_PATH

    def _load_prefs(self) -> Dict[str, bool]:
        path = self._prefs_path()
        if not path.exists():
            self._prefs = {}
            return self._prefs
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            enabled = data.get("enabled") if isinstance(data, dict) else {}
            if not isinstance(enabled, dict):
                enabled = {}
            self._prefs = {str(k): bool(v) for k, v in enabled.items()}
        except Exception:
            logger.exception("Failed reading plugin prefs %s", path)
            self._prefs = {}
        return self._prefs

    def _save_prefs(self) -> None:
        path = self._prefs_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"enabled": self._prefs}
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _apply_prefs(self, manifest: PluginManifest) -> PluginManifest:
        if manifest.plugin_id in self._prefs:
            manifest.enabled = self._prefs[manifest.plugin_id]
        return manifest

    def _set_pref(self, plugin_id: str, enabled: bool) -> None:
        self._prefs[plugin_id] = enabled
        try:
            self._save_prefs()
        except Exception:
            logger.exception("Failed writing plugin prefs")

    async def bootstrap(self) -> None:
        self._load_prefs()
        root = Path(self.settings.plugins_dir)
        root.mkdir(parents=True, exist_ok=True)
        (root / "mcp").mkdir(exist_ok=True)
        (root / "cli").mkdir(exist_ok=True)

        # Load MCP manifests
        for manifest_path in sorted((root / "mcp").glob("*.json")):
            try:
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest = self._apply_prefs(PluginManifest.model_validate(data))
                await self.load(manifest)
            except Exception:
                logger.exception("Failed loading MCP manifest %s", manifest_path)

        if self.settings.cli_auto_register:
            await self.scan_cli_directory(root / "cli")

        # Built-in echo tool for zero-config demos
        if "builtin.echo" not in self.plugins:
            await self.load(self._apply_prefs(_InProcessEchoManifest()))
        if "builtin.workspace" not in self.plugins:
            await self.load(self._apply_prefs(workspace_tools_manifest()))
        if "builtin.subagent" not in self.plugins:
            await self.load(self._apply_prefs(subagent_tools_manifest()))
        if "builtin.knowledge" not in self.plugins:
            await self.load(self._apply_prefs(knowledge_tools_manifest()))
        if "builtin.image_gen" not in self.plugins:
            await self.load(self._apply_prefs(image_gen_manifest()))

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
            manifest = self._discover_manifest(plugin_id)
            if manifest is None:
                continue
            await self.load(self._apply_prefs(manifest))

    async def load(self, manifest: PluginManifest) -> PluginManifest:
        async with self._lock:
            if manifest.plugin_id in self.plugins:
                await self.unload(manifest.plugin_id)
            plugin = self._create(manifest)
            try:
                if manifest.enabled:
                    await plugin.init()
                    await plugin.ready()
                else:
                    # Defer heavy init (e.g. MCP stdio/npx) until explicitly enabled
                    plugin.state = PluginState.DISABLED
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
            if manifest.plugin_id == "builtin.workspace":
                return WorkspaceToolsPlugin(manifest)
            if manifest.plugin_id == "builtin.subagent":
                return SubagentToolsPlugin(manifest)
            if manifest.plugin_id == "builtin.knowledge":
                return KnowledgeToolsPlugin(manifest)
            if manifest.plugin_id == "builtin.image_gen":
                return ImageGenPlugin(manifest)
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
        plugin.manifest.enabled = True
        self._set_pref(plugin_id, True)

    async def disable(self, plugin_id: str) -> None:
        plugin = self._require(plugin_id)
        await plugin.disable()
        plugin.manifest.enabled = False
        self._set_pref(plugin_id, False)

    def list_plugins(self) -> List[Dict[str, Any]]:
        out = []
        for p in self.plugins.values():
            tools = []
            for tool in p.manifest.tools or []:
                name = tool.get("name") or "tool"
                tools.append(
                    {
                        "name": name,
                        "description": tool.get("description") or "",
                        "inputSchema": tool.get("inputSchema")
                        or tool.get("parameters")
                        or {"type": "object", "properties": {}},
                        "openai_name": self.openai_tool_name(p.plugin_id, name),
                    }
                )
            out.append(
                {
                    "plugin_id": p.plugin_id,
                    "name": p.manifest.name,
                    "kind": p.manifest.kind,
                    "version": p.manifest.version,
                    "description": p.manifest.description or "",
                    "state": p.state.value,
                    "enabled": bool(p.manifest.enabled),
                    "active": p.state == PluginState.READY,
                    "tools": tools if p.state == PluginState.READY else [],
                    "tool_count": len(p.manifest.tools or []),
                    "last_error": p.last_error,
                    "health": p.health_summary(),
                    "config_hints": self._config_hints(p),
                    "config_schema": get_plugin_config_store().public_view(p.plugin_id)
                    if p.plugin_id in PLUGIN_CONFIG_SCHEMAS
                    else None,
                }
            )
        return out

    def _config_hints(self, plugin: BasePlugin) -> List[str]:
        hints: List[str] = []
        import os

        store = get_plugin_config_store()
        cfg = store.get(plugin.plugin_id)
        if plugin.plugin_id in ("cli.web_search",) or any(
            (t.get("name") == "web_search") for t in (plugin.manifest.tools or [])
        ):
            tavily = cfg.get("TAVILY_API_KEY") or os.environ.get("TAVILY_API_KEY") or self.settings.tavily_api_key
            brave = cfg.get("BRAVE_API_KEY") or os.environ.get("BRAVE_API_KEY") or getattr(
                self.settings, "brave_api_key", ""
            )
            if not tavily:
                hints.append("未配置 Tavily Key：可在插件卡片里填写，不必改 .env。")
            if not brave:
                hints.append("可选：配置 Brave Search Key 作为备用。")
        if plugin.plugin_id == "builtin.image_gen":
            if not (cfg.get("IMAGE_MODEL") or cfg.get("IMAGE_PROVIDER")):
                hints.append("启用后请在插件配置中填写生图 Provider / 模型。")
        if plugin.plugin_id == "cli.literature_search":
            hints.append("默认使用 OpenAlex 免费检索；可选填 Semantic Scholar Key。")
        if plugin.plugin_id == "cli.image_search":
            has_any = any(
                cfg.get(k) or os.environ.get(k)
                for k in (
                    "SERPAPI_API_KEY",
                    "BING_SEARCH_API_KEY",
                    "AZURE_BING_SEARCH_KEY",
                    "BRAVE_API_KEY",
                    "UNSPLASH_ACCESS_KEY",
                    "PEXELS_API_KEY",
                )
            )
            if not has_any:
                hints.append(
                    "未配置搜图 Key：建议填 SerpAPI（Google 图）或 Bing / Unsplash / Pexels；"
                    "也可复用 Brave Key。无 Key 时尝试免费 DuckDuckGo。"
                )
        if plugin.plugin_id == "cli.web_crawl":
            hints.append(
                "基于 Crawl4AI（Playwright 无头浏览器）。首次需: pip install crawl4ai && crawl4ai-setup"
            )
        return hints

    def get_plugin_config(self, plugin_id: str) -> Dict[str, Any]:
        self._require(plugin_id)
        return get_plugin_config_store().public_view(plugin_id)

    def set_plugin_config(self, plugin_id: str, values: Dict[str, Any]) -> Dict[str, Any]:
        self._require(plugin_id)
        return get_plugin_config_store().upsert(plugin_id, values)

    def list_tools(self) -> List[Dict[str, Any]]:
        tools: List[Dict[str, Any]] = []
        for p in self.plugins.values():
            if p.state != PluginState.READY:
                continue
            for tool in p.manifest.tools:
                name = tool.get("name") or "tool"
                schema = tool.get("inputSchema") or tool.get("parameters") or {
                    "type": "object",
                    "properties": {},
                }
                tools.append(
                    {
                        "name": name,
                        "description": tool.get("description")
                        or f"{p.manifest.name}: {name}",
                        "inputSchema": schema,
                        "parameters": schema,
                        "plugin_id": p.plugin_id,
                        "openai_name": self.openai_tool_name(p.plugin_id, name),
                    }
                )
        return tools

    async def reload(self, plugin_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Rescan disk and reload one plugin, or all plugins when plugin_id is None."""
        if self._inflight_invokes > 0:
            raise PluginError(
                f"cannot reload while {self._inflight_invokes} plugin invoke(s) in flight"
            )
        if plugin_id:
            await self._reload_one(plugin_id)
        else:
            await self.reload_all()
        return self.list_plugins()

    async def reload_all(self) -> None:
        async with self._lock:
            ids = list(self.plugins.keys())
            for pid in ids:
                plugin = self.plugins.pop(pid, None)
                if not plugin:
                    continue
                try:
                    await plugin.teardown()
                except Exception:
                    logger.exception("Teardown failed for %s during reload_all", pid)
        await self.bootstrap()

    async def _reload_one(self, plugin_id: str) -> None:
        manifest = self._discover_manifest(plugin_id)
        if manifest is None:
            # Keep in-memory plugin if present: unload + load same manifest
            existing = self.plugins.get(plugin_id)
            if not existing:
                raise NotFoundError(f"plugin not found: {plugin_id}")
            manifest = existing.manifest.model_copy(deep=True)
        await self.load(self._apply_prefs(manifest))

    def _discover_manifest(self, plugin_id: str) -> Optional[PluginManifest]:
        if plugin_id == "builtin.echo":
            return _InProcessEchoManifest()
        if plugin_id == "builtin.workspace":
            return workspace_tools_manifest()
        if plugin_id == "builtin.subagent":
            return subagent_tools_manifest()
        if plugin_id == "builtin.knowledge":
            return knowledge_tools_manifest()
        if plugin_id == "builtin.image_gen":
            return image_gen_manifest()

        root = Path(self.settings.plugins_dir)
        for manifest_path in (root / "mcp").glob("*.json"):
            try:
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
                if data.get("plugin_id") == plugin_id:
                    return PluginManifest.model_validate(data)
            except Exception:
                continue

        if plugin_id.startswith("cli."):
            stem = plugin_id[4:]
            cli_dir = root / "cli"
            for path in cli_dir.iterdir() if cli_dir.exists() else []:
                if path.is_file() and path.stem == stem:
                    description = f"Auto-registered CLI tool from {path.name}"
                    tools: List[Dict[str, Any]] = []
                    if path.stem == "web_search":
                        description = (
                            "Search the live internet and return titles, URLs, and snippets. "
                            "Use for current events, facts, docs, or anything needing up-to-date web info. "
                            "When citing findings, list source URLs as references at the end of your reply."
                        )
                        tools = [
                            {
                                "name": "web_search",
                                "description": description,
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "query": {
                                            "type": "string",
                                            "description": "Search query in natural language",
                                        },
                                        "max_results": {
                                            "type": "integer",
                                            "description": "Number of results (1-10, default 5)",
                                        },
                                    },
                                    "required": ["query"],
                                },
                            }
                        ]
                    elif path.stem == "literature_search":
                        description = (
                            "Search academic literature / papers (OpenAlex). Returns titles, authors, years, "
                            "DOI/URLs and a ready-to-paste References markdown block. "
                            "Prefer this over web_search for papers, inhibitors, PubMed/DOI topics. "
                            "Always include references_md (or equivalent citation list with URLs) in your reply. "
                            "Do NOT ask the user for a year cutoff unless they care — omit year_from to search broadly."
                        )
                        tools = [
                            {
                                "name": "literature_search",
                                "description": description,
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "query": {"type": "string", "description": "Paper / topic query"},
                                        "max_results": {"type": "integer", "description": "1-10, default 5"},
                                        "year_from": {
                                            "type": "integer",
                                            "description": "Optional earliest publication year",
                                        },
                                    },
                                    "required": ["query"],
                                },
                            }
                        ]
                    elif path.stem == "image_search":
                        description = (
                            "Search the web for images (SerpAPI Google Images / Bing / Brave / Unsplash / Pexels). "
                            "Returns image URLs and a `markdown` gallery. "
                            "ALWAYS paste the returned markdown into your assistant reply so images render in chat."
                        )
                        tools = [
                            {
                                "name": "image_search",
                                "description": description,
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "query": {
                                            "type": "string",
                                            "description": "Image search query (natural language)",
                                        },
                                        "max_results": {
                                            "type": "integer",
                                            "description": "Number of images (1-12, default 6)",
                                        },
                                    },
                                    "required": ["query"],
                                },
                            }
                        ]
                    elif path.stem == "weknora_search":
                        # Prefer in-process KnowledgeToolsPlugin.weknora_search
                        # (workspace/session KB routing). CLI script remains for
                        # standalone use; do not register a duplicate OpenAI tool.
                        return None
                    elif path.stem == "web_crawl":
                        description = (
                            "Crawl a specific URL with Crawl4AI (headless browser) and return clean Markdown "
                            "suitable for LLM reading. Use when you already have a URL and need the full page "
                            "content (docs, blogs, papers landing pages) — not for open-ended search "
                            "(use web_search / literature_search for that). "
                            "Summarize the markdown; do not dump the entire page into chat unless asked."
                        )
                        tools = [
                            {
                                "name": "web_crawl",
                                "description": description,
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "url": {
                                            "type": "string",
                                            "description": "Absolute http(s) URL to crawl",
                                        },
                                        "max_chars": {
                                            "type": "integer",
                                            "description": "Max markdown chars to return (default 40000)",
                                        },
                                        "wait_for": {
                                            "type": "string",
                                            "description": "Optional CSS selector to wait for before extract",
                                        },
                                    },
                                    "required": ["url"],
                                },
                            }
                        ]
                    if path.suffix.lower() == ".py":
                        script = str(path.resolve())
                        timeout = 45
                        if path.stem in {"web_search", "literature_search", "image_search"}:
                            timeout = 55
                        if path.stem == "web_crawl":
                            timeout = 120
                        config = {
                            # Same interpreter as the kernel (project .venv), not bare PATH "python".
                            "script": sys.executable,
                            "tool_name": path.stem,
                            "input_mode": "stdin_json",
                            "timeout": timeout,
                            "_args_prefix": [script],
                        }
                    else:
                        config = {
                            "script": str(path.resolve()),
                            "tool_name": path.stem,
                            "input_mode": "stdin_json",
                        }
                    return PluginManifest(
                        plugin_id=plugin_id,
                        name=path.stem,
                        kind="cli",
                        description=description,
                        tools=tools,
                        config=config,
                    )
        return None

    def as_openai_tools(self) -> List[Dict[str, Any]]:
        """OpenAI-compatible tools list for chat completions."""
        out: List[Dict[str, Any]] = []
        for p in self.plugins.values():
            if p.state != PluginState.READY:
                continue
            for tool in p.manifest.tools:
                name = tool.get("name") or "tool"
                fn_name = self.openai_tool_name(p.plugin_id, name)
                params = tool.get("inputSchema") or tool.get("parameters") or {
                    "type": "object",
                    "properties": {},
                }
                out.append(
                    {
                        "type": "function",
                        "function": {
                            "name": fn_name,
                            "description": tool.get("description")
                            or f"{p.manifest.name}: {name}",
                            "parameters": params,
                        },
                    }
                )
        return out

    def tool_name_map(self) -> Dict[str, tuple[str, str]]:
        """Map openai function name → (plugin_id, tool_name)."""
        mapping: Dict[str, tuple[str, str]] = {}
        for p in self.plugins.values():
            if p.state != PluginState.READY:
                continue
            for tool in p.manifest.tools:
                name = tool.get("name") or "tool"
                fn_name = self.openai_tool_name(p.plugin_id, name)
                mapping[fn_name] = (p.plugin_id, name)
                mapping[name] = (p.plugin_id, name)
        return mapping

    async def invoke(self, req: PluginInvokeRequest, *, task_id: Optional[str] = None) -> PluginInvokeResult:
        plugin = self._require(req.plugin_id)
        started = time.perf_counter()
        success = True
        error: Optional[str] = None
        result: Any = None
        self._inflight_invokes += 1
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
        finally:
            self._inflight_invokes = max(0, self._inflight_invokes - 1)
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
