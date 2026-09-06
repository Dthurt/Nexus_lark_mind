"""Anthropic Messages API provider."""

from __future__ import annotations

import json
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

from src.common.config import Settings
from src.common.errors import ModelGatewayError
from src.common.schemas import ChatMessage, ChatRole, ModelChunk, ModelRequest, ModelResponse
from src.core_kernel.model_gateway.base import BaseModelProvider


class AnthropicProvider(BaseModelProvider):
    name = "anthropic"

    def __init__(self, settings: Optional[Settings] = None) -> None:
        super().__init__(settings)
        self.api_key = self.settings.anthropic_api_key
        self.base_url = self.settings.anthropic_base_url.rstrip("/")
        self.default_model = "claude-3-5-sonnet-20241022"

    def _headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }

    def _split_messages(self, messages: List[ChatMessage]) -> tuple[Optional[str], List[Dict[str, Any]]]:
        system_parts: List[str] = []
        converted: List[Dict[str, Any]] = []
        for m in messages:
            if m.role == ChatRole.SYSTEM:
                system_parts.append(m.content)
                continue
            role = "assistant" if m.role == ChatRole.ASSISTANT else "user"
            if m.role == ChatRole.TOOL:
                role = "user"
            converted.append({"role": role, "content": m.content})
        system = "\n".join(system_parts) if system_parts else None
        return system, converted

    async def complete(self, request: ModelRequest) -> ModelResponse:
        if not self.api_key:
            text = (
                "[Nexus-Lark-Mind demo mode] Anthropic key missing. "
                f"Echo last user turn."
            )
            for m in reversed(request.messages):
                if m.role == ChatRole.USER:
                    text = f"[demo anthropic] {m.content}"
                    break
            return ModelResponse(
                content=text,
                finish_reason="end_turn",
                provider=self.name,
                model=request.model or self.default_model,
            )

        system, msgs = self._split_messages(request.messages)
        payload: Dict[str, Any] = {
            "model": request.model or self.default_model,
            "messages": msgs,
            "max_tokens": request.max_tokens or 2048,
            "temperature": request.temperature,
            "stream": False,
        }
        if system:
            payload["system"] = system

        url = f"{self.base_url}/v1/messages"
        async with httpx.AsyncClient(timeout=self.settings.model_timeout_seconds) as client:
            resp = await client.post(url, headers=self._headers(), json=payload)
            if resp.status_code >= 400:
                raise ModelGatewayError(f"anthropic HTTP {resp.status_code}: {resp.text}")
            data = resp.json()

        content_blocks = data.get("content") or []
        text = "".join(b.get("text", "") for b in content_blocks if b.get("type") == "text")
        usage = data.get("usage") or {}
        return ModelResponse(
            content=text,
            finish_reason=data.get("stop_reason"),
            usage={
                "prompt_tokens": usage.get("input_tokens", 0),
                "completion_tokens": usage.get("output_tokens", 0),
            },
            provider=self.name,
            model=data.get("model") or request.model or self.default_model,
        )

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelChunk]:
        if not self.api_key:
            result = await self.complete(request)
            yield ModelChunk(content=result.content)
            yield ModelChunk(content="", finish_reason="end_turn")
            return

        system, msgs = self._split_messages(request.messages)
        payload: Dict[str, Any] = {
            "model": request.model or self.default_model,
            "messages": msgs,
            "max_tokens": request.max_tokens or 2048,
            "temperature": request.temperature,
            "stream": True,
        }
        if system:
            payload["system"] = system

        url = f"{self.base_url}/v1/messages"
        async with httpx.AsyncClient(timeout=self.settings.model_timeout_seconds) as client:
            async with client.stream("POST", url, headers=self._headers(), json=payload) as resp:
                if resp.status_code >= 400:
                    body = await resp.aread()
                    raise ModelGatewayError(f"anthropic stream HTTP {resp.status_code}: {body.decode()}")
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    if not raw:
                        continue
                    try:
                        data = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    etype = data.get("type")
                    if etype == "content_block_delta":
                        delta = data.get("delta") or {}
                        if delta.get("type") == "text_delta":
                            yield ModelChunk(content=delta.get("text") or "")
                    elif etype == "message_stop":
                        yield ModelChunk(content="", finish_reason="end_turn")
