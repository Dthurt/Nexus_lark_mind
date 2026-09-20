"""Builtin image generation via OpenAI-compatible /images/generations."""

from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

import httpx

from src.common.config import get_settings
from src.common.errors import PluginError
from src.core_kernel.model_gateway.provider_store import ProviderStore
from src.core_kernel.plugin_runtime.lifecycle import BasePlugin, PluginManifest
from src.core_kernel.plugin_runtime.plugin_config_store import get_plugin_config_store

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
IMAGE_DIR = _REPO_ROOT / "data" / "generated_images"

TOOLS: List[Dict[str, Any]] = [
    {
        "name": "generate_image",
        "description": (
            "Generate an image from a text prompt using the configured image model "
            "(OpenAI-compatible /images/generations). Returns a local markdown image URL "
            "you MUST include in your reply so the user can see it in chat."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Image description"},
                "size": {
                    "type": "string",
                    "description": "e.g. 1024x1024",
                },
                "model": {"type": "string", "description": "Override image model id"},
            },
            "required": ["prompt"],
        },
    }
]


class ImageGenPlugin(BasePlugin):
    async def _on_init(self) -> None:
        return None

    async def _on_ready(self) -> None:
        self.manifest.tools = list(TOOLS)

    async def _on_teardown(self) -> None:
        return None

    def _resolve_endpoint(self) -> tuple[str, str, str, str]:
        cfg = get_plugin_config_store().get("builtin.image_gen")
        settings = get_settings()
        store = ProviderStore()
        plugin_provider = (cfg.get("IMAGE_PROVIDER") or "").strip()
        provider_id = (
            plugin_provider
            or (store.default_image_provider or "")
            or ""
        ).strip()
        if not provider_id:
            images = [p for p in store.providers_of_kind("image") if p.enabled]
            if images:
                provider_id = images[0].id
        if not provider_id:
            provider_id = (
                store.default_provider or settings.default_model_provider or ""
            ).strip()
        model = (cfg.get("IMAGE_MODEL") or "").strip()
        size = (cfg.get("IMAGE_SIZE") or "1024x1024").strip()

        base_url = ""
        api_key = ""
        if provider_id in store.providers:
            p = store.providers[provider_id]
            base_url = p.base_url
            api_key = p.api_key
            if not model:
                model = p.default_model
        else:
            mapping = {
                "openai": (settings.openai_base_url, settings.openai_api_key, settings.openai_default_model),
                "deepseek": (settings.deepseek_base_url, settings.deepseek_api_key, settings.deepseek_default_model),
                "glm": (settings.glm_base_url, settings.glm_api_key, settings.glm_default_model),
            }
            if provider_id in mapping:
                base_url, api_key, default_model = mapping[provider_id]
                if not model:
                    model = default_model
        if not base_url or not api_key:
            raise PluginError(
                "Image generation not configured. Add a 生图模型 in Settings → 模型, "
                "or set IMAGE_PROVIDER / API key on a custom OpenAI-compat provider."
            )
        if not model:
            model = "dall-e-3"
        return base_url.rstrip("/"), api_key, model, size

    async def _on_invoke(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        if tool_name != "generate_image":
            raise PluginError(f"unknown tool: {tool_name}")
        prompt = str(arguments.get("prompt") or "").strip()
        if not prompt:
            raise PluginError("prompt required")
        base_url, api_key, default_model, default_size = self._resolve_endpoint()
        model = str(arguments.get("model") or default_model).strip()
        size = str(arguments.get("size") or default_size).strip() or "1024x1024"

        url = f"{base_url}/images/generations"
        payload = {"model": model, "prompt": prompt, "n": 1, "size": size}
        # Prefer b64 to save locally
        payload["response_format"] = "b64_json"

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                url,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
            )
            if resp.status_code >= 400:
                # Some gateways reject response_format — retry without
                if "response_format" in payload:
                    payload.pop("response_format", None)
                    resp = await client.post(
                        url,
                        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                        json=payload,
                    )
                if resp.status_code >= 400:
                    raise PluginError(f"image API {resp.status_code}: {resp.text[:500]}")
            data = resp.json()

        items = data.get("data") or []
        if not items:
            raise PluginError("image API returned no data")
        item = items[0]
        IMAGE_DIR.mkdir(parents=True, exist_ok=True)
        file_id = uuid4().hex[:16]
        path = IMAGE_DIR / f"{file_id}.png"
        b64 = item.get("b64_json")
        remote_url = item.get("url")
        if b64:
            path.write_bytes(base64.b64decode(b64))
        elif remote_url:
            async with httpx.AsyncClient(timeout=60.0) as client:
                r = await client.get(remote_url)
                r.raise_for_status()
                path.write_bytes(r.content)
        else:
            raise PluginError("image API missing b64_json and url")

        local_url = f"/api/generated-images/{file_id}.png"
        md = f"![{prompt[:60]}]({local_url})"
        return {
            "ok": True,
            "prompt": prompt,
            "model": model,
            "size": size,
            "url": local_url,
            "markdown": md,
            "hint": "Include the markdown image in your assistant reply so it renders in chat.",
        }


def image_gen_manifest() -> PluginManifest:
    return PluginManifest(
        plugin_id="builtin.image_gen",
        name="Image Generation",
        kind="inprocess",
        version="0.1.0",
        description="Generate images via OpenAI-compatible image APIs. Disable when unused.",
        enabled=False,  # opt-in
        tools=list(TOOLS),
        config={},
    )
