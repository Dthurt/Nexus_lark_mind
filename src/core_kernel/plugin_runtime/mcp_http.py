"""MCP over HTTP — remote plugin transport."""

from __future__ import annotations

from typing import Any, Dict, Optional

import httpx

from src.common.errors import PluginError
from src.core_kernel.plugin_runtime.lifecycle import BasePlugin, PluginManifest


class McpHttpPlugin(BasePlugin):
    def __init__(self, manifest: PluginManifest) -> None:
        super().__init__(manifest)
        self._client: Optional[httpx.AsyncClient] = None
        self.endpoint = (manifest.config.get("url") or "").rstrip("/")

    async def _on_init(self) -> None:
        if not self.endpoint:
            raise PluginError(f"mcp_http plugin {self.plugin_id} missing url")
        self._client = httpx.AsyncClient(timeout=60.0)

    async def _on_ready(self) -> None:
        assert self._client is not None
        # Soft health probe
        try:
            resp = await self._client.get(f"{self.endpoint}/health")
            if resp.status_code >= 500:
                raise PluginError(f"remote plugin unhealthy: {resp.status_code}")
        except httpx.HTTPError:
            # Many MCP HTTP servers have no /health — tolerate
            pass
        try:
            listed = await self._rpc("tools/list", {})
            if isinstance(listed, dict) and listed.get("tools"):
                self.manifest.tools = listed["tools"]
        except Exception:
            pass

    async def _on_invoke(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        return await self._rpc("tools/call", {"name": tool_name, "arguments": arguments})

    async def _on_teardown(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _rpc(self, method: str, params: Dict[str, Any]) -> Any:
        if not self._client:
            raise PluginError(f"plugin {self.plugin_id} http client missing")
        payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        path = self.manifest.config.get("rpc_path", "/mcp")
        resp = await self._client.post(f"{self.endpoint}{path}", json=payload)
        if resp.status_code >= 400:
            raise PluginError(f"mcp http {resp.status_code}: {resp.text}")
        data = resp.json()
        if "error" in data:
            raise PluginError(str(data["error"]))
        return data.get("result")
