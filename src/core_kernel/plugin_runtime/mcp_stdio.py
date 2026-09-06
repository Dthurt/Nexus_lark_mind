"""MCP over stdio — local subprocess plugin transport."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, Optional

from src.common.errors import PluginError
from src.core_kernel.plugin_runtime.lifecycle import BasePlugin, PluginManifest

logger = logging.getLogger(__name__)


class McpStdioPlugin(BasePlugin):
    """Minimal JSON-RPC MCP-stdio client for tools/list + tools/call."""

    def __init__(self, manifest: PluginManifest) -> None:
        super().__init__(manifest)
        self._proc: Optional[asyncio.subprocess.Process] = None
        self._req_id = 0
        self._lock = asyncio.Lock()

    async def _on_init(self) -> None:
        command = self.manifest.config.get("command")
        args = self.manifest.config.get("args") or []
        if not command:
            raise PluginError(f"mcp_stdio plugin {self.plugin_id} missing command")
        self._proc = await asyncio.create_subprocess_exec(
            command,
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

    async def _on_ready(self) -> None:
        # Initialize handshake (best-effort; tolerant for demo servers)
        try:
            await self._rpc("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "nexus-lark-mind", "version": "1.0.0"},
            })
            await self._notify("notifications/initialized", {})
            listed = await self._rpc("tools/list", {})
            tools = listed.get("tools") if isinstance(listed, dict) else None
            if tools:
                self.manifest.tools = tools
        except Exception as exc:
            logger.warning("MCP stdio ready handshake soft-fail for %s: %s", self.plugin_id, exc)

    async def _on_invoke(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        return await self._rpc(
            "tools/call",
            {"name": tool_name, "arguments": arguments},
        )

    async def _on_teardown(self) -> None:
        if self._proc and self._proc.returncode is None:
            self._proc.terminate()
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                self._proc.kill()
        self._proc = None

    async def _notify(self, method: str, params: Dict[str, Any]) -> None:
        msg = {"jsonrpc": "2.0", "method": method, "params": params}
        await self._write(msg)

    async def _rpc(self, method: str, params: Dict[str, Any]) -> Any:
        async with self._lock:
            self._req_id += 1
            req_id = self._req_id
            msg = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}
            await self._write(msg)
            return await self._read_response(req_id)

    async def _write(self, msg: Dict[str, Any]) -> None:
        if not self._proc or not self._proc.stdin:
            raise PluginError(f"plugin {self.plugin_id} process not running")
        body = json.dumps(msg).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        self._proc.stdin.write(header + body)
        await self._proc.stdin.drain()

    async def _read_response(self, req_id: int, timeout: float = 30.0) -> Any:
        if not self._proc or not self._proc.stdout:
            raise PluginError(f"plugin {self.plugin_id} stdout missing")

        async def _read_one() -> Dict[str, Any]:
            # Content-Length framed or newline JSON fallback
            header = await self._proc.stdout.readline()
            if not header:
                raise PluginError(f"plugin {self.plugin_id} closed stdout")
            if header.lower().startswith(b"content-length:"):
                length = int(header.split(b":")[1].strip())
                # consume remaining headers
                while True:
                    line = await self._proc.stdout.readline()
                    if line in (b"\r\n", b"\n", b""):
                        break
                body = await self._proc.stdout.readexactly(length)
                return json.loads(body)
            # newline-delimited JSON
            return json.loads(header.decode("utf-8"))

        deadline = asyncio.get_event_loop().time() + timeout
        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                raise PluginError(f"plugin {self.plugin_id} RPC timeout")
            msg = await asyncio.wait_for(_read_one(), timeout=remaining)
            if msg.get("id") == req_id:
                if "error" in msg:
                    raise PluginError(str(msg["error"]))
                return msg.get("result")
