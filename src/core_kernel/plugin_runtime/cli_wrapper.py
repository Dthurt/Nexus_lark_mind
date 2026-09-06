"""Wrap arbitrary local CLI scripts as Agent tools."""

from __future__ import annotations

import asyncio
import json
import shlex
import shutil
from pathlib import Path
from typing import Any, Dict

from src.common.errors import PluginError
from src.core_kernel.plugin_runtime.lifecycle import BasePlugin, PluginManifest


class CliPlugin(BasePlugin):
    """
    Invokes a local executable/script.
    Arguments are passed as JSON on stdin by default, or as CLI flags when configured.
    """

    async def _on_init(self) -> None:
        script = self.manifest.config.get("script")
        if not script:
            raise PluginError(f"cli plugin {self.plugin_id} missing script")
        path = Path(script)
        if not path.exists() and shutil.which(script) is None:
            raise PluginError(f"cli script not found: {script}")

    async def _on_ready(self) -> None:
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

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE if stdin_data is not None else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
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
