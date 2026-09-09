"""Wrap arbitrary local CLI scripts as Agent tools."""

from __future__ import annotations

import asyncio
import json
import os
import shlex
import shutil
from pathlib import Path
from typing import Any, Dict

from src.common.config import get_settings
from src.common.errors import PluginError
from src.core_kernel.plugin_runtime.invoke_context import get_workspace_cwd
from src.core_kernel.plugin_runtime.lifecycle import BasePlugin, PluginManifest


class CliPlugin(BasePlugin):
    """
    Invokes a local executable/script.
    Arguments are passed as JSON on stdin by default, or as CLI flags when configured.
    """

    def _child_env(self) -> Dict[str, str]:
        env = os.environ.copy()
        extra = self.manifest.config.get("env") or {}
        for k, v in extra.items():
            if v is not None and str(v) != "":
                env[str(k)] = str(v)
        # Inject search keys from app settings if not already present
        settings = get_settings()
        if settings.tavily_api_key and not env.get("TAVILY_API_KEY"):
            env["TAVILY_API_KEY"] = settings.tavily_api_key
        if settings.tavily_search_depth and not env.get("TAVILY_SEARCH_DEPTH"):
            env["TAVILY_SEARCH_DEPTH"] = settings.tavily_search_depth
        brave = getattr(settings, "brave_api_key", "") or ""
        if brave and not env.get("BRAVE_API_KEY"):
            env["BRAVE_API_KEY"] = brave
        cwd = get_workspace_cwd()
        if cwd:
            env["NLM_WORKSPACE_CWD"] = cwd
            meta = __import__(
                "src.core_kernel.plugin_runtime.invoke_context", fromlist=["get_workspace_meta"]
            ).get_workspace_meta()
            if meta.get("workspace_kind") == "ssh":
                env["NLM_WORKSPACE_KIND"] = "ssh"
                if meta.get("ssh_host_id"):
                    env["NLM_SSH_HOST_ID"] = str(meta["ssh_host_id"])
        return env

    async def _on_init(self) -> None:
        script = self.manifest.config.get("script")
        if not script:
            raise PluginError(f"cli plugin {self.plugin_id} missing script")
        path = Path(script)
        if not path.exists() and shutil.which(script) is None:
            raise PluginError(f"cli script not found: {script}")

    async def _on_ready(self) -> None:
        # Allow manifests / auto-register to supply richer tool schemas
        if self.manifest.tools:
            return
        tool_name = self.manifest.config.get("tool_name") or self.plugin_id
        self.manifest.tools = [
            {
                "name": tool_name,
                "description": self.manifest.description or f"CLI tool {tool_name}",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "args": {"type": "string", "description": "extra CLI args"},
                        "input": {"type": "object", "description": "JSON payload via stdin"},
                    },
                },
            }
        ]

    async def _on_invoke(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        script = self.manifest.config["script"]
        timeout = float(self.manifest.config.get("timeout", 60))
        mode = self.manifest.config.get("input_mode", "stdin_json")
        extra = arguments.get("args") or ""
        prefix = list(self.manifest.config.get("_args_prefix") or [])
        cmd = [script, *prefix, *shlex.split(str(extra))] if extra else [script, *prefix]

        stdin_data = None
        if mode == "stdin_json":
            payload = arguments.get("input", arguments)
            stdin_data = json.dumps(payload).encode("utf-8")

        from src.core_kernel.plugin_runtime.invoke_context import get_workspace_cwd, get_workspace_meta

        meta = get_workspace_meta()
        cwd = None
        # Remote SSH cwd is not a local path — don't pass to subprocess
        if (meta.get("workspace_kind") or "") != "ssh":
            cwd = get_workspace_cwd() or None
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE if stdin_data is not None else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=self._child_env(),
            cwd=cwd,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(stdin_data),
                timeout=timeout,
            )
        except asyncio.TimeoutError as exc:
            proc.kill()
            raise PluginError(f"cli plugin timeout: {self.plugin_id}") from exc

        if proc.returncode != 0:
            raise PluginError(
                f"cli exited {proc.returncode}: {stderr.decode('utf-8', errors='ignore')}"
            )
        text = stdout.decode("utf-8", errors="ignore").strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"stdout": text}

    async def _on_teardown(self) -> None:
        return None
