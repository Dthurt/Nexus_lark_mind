"""OpenAI-compatible provider (OpenAI, DeepSeek, GLM, local proxies)."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

from src.common.config import Settings
from src.common.errors import ModelGatewayError, RateLimitError
from src.common.schemas import ChatMessage, ChatRole, ModelChunk, ModelRequest, ModelResponse
from src.core_kernel.model_gateway.base import BaseModelProvider
from src.core_kernel.model_gateway.retry import (
    compute_backoff_seconds,
    format_rate_limit_exhausted,
    format_retry_notice,
    raise_if_rate_limited,
)

logger = logging.getLogger(__name__)


def _messages_to_openai(messages: List[ChatMessage]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for m in messages:
        item: Dict[str, Any] = {"role": m.role.value, "content": m.content}
        if m.name:
            item["name"] = m.name
        if m.tool_call_id:
            item["tool_call_id"] = m.tool_call_id
        out.append(item)
    return out


class OpenAICompatProvider(BaseModelProvider):
    def __init__(
        self,
        *,
        name: str,
        api_key: str,
        base_url: str,
        default_model: str,
        settings: Optional[Settings] = None,
    ) -> None:
        super().__init__(settings)
        self.name = name
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _payload(self, request: ModelRequest, stream: bool) -> Dict[str, Any]:
        model = request.model or self.default_model
        payload: Dict[str, Any] = {
            "model": model,
            "messages": _messages_to_openai(request.messages),
            "temperature": request.temperature,
            "stream": stream,
        }
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        if request.tools:
            payload["tools"] = request.tools
        return payload

    def _retry_budget(self) -> tuple[int, float, float]:
        return (
            max(0, int(self.settings.model_max_retries)),
            float(self.settings.model_retry_base_seconds),
            float(self.settings.model_retry_max_seconds),
        )

    async def complete(self, request: ModelRequest) -> ModelResponse:
        if not self.api_key:
            text = self._echo_fallback(request)
            return ModelResponse(
                content=text,
                finish_reason="stop",
                provider=self.name,
                model=request.model or self.default_model,
            )

        max_retries, base, maximum = self._retry_budget()
        attempt = 0
        while True:
            try:
                return await self._complete_once(request)
            except RateLimitError as exc:
                if attempt >= max_retries:
                    raise RateLimitError(
                        format_rate_limit_exhausted(max_retries),
                        detail=str(exc),
                        retry_after=exc.retry_after,
                    ) from exc
                wait = compute_backoff_seconds(
                    attempt,
                    base=base,
                    maximum=maximum,
                    retry_after=exc.retry_after,
                )
                logger.warning(
                    "%s complete rate-limited, retry %s/%s in %.1fs",
                    self.name,
                    attempt + 1,
                    max_retries,
                    wait,
                )
                await asyncio.sleep(wait)
                attempt += 1

    async def _complete_once(self, request: ModelRequest) -> ModelResponse:
        url = f"{self.base_url}/chat/completions"
        payload = self._payload(request, stream=False)
        timeout = self.settings.model_timeout_seconds
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, headers=self._headers(), json=payload)
            if resp.status_code >= 400:
                raise_if_rate_limited(resp.status_code, resp.text, dict(resp.headers))
                raise ModelGatewayError(f"{self.name} HTTP {resp.status_code}: {resp.text}")
            data = resp.json()

        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        usage = data.get("usage") or {}
        return ModelResponse(
            content=message.get("content") or "",
            finish_reason=choice.get("finish_reason"),
            tool_calls=message.get("tool_calls") or [],
            usage=usage,
            provider=self.name,
            model=data.get("model") or request.model or self.default_model,
        )

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelChunk]:
        if not self.api_key:
            text = self._echo_fallback(request)
            for i in range(0, len(text), 24):
                yield ModelChunk(content=text[i : i + 24])
            yield ModelChunk(content="", finish_reason="stop")
            return

        max_retries, base, maximum = self._retry_budget()
        attempt = 0
        while True:
            try:
                async for chunk in self._stream_once(request):
                    yield chunk
                return
            except RateLimitError as exc:
                if attempt >= max_retries:
                    raise RateLimitError(
                        format_rate_limit_exhausted(max_retries),
                        detail=str(exc),
                        retry_after=exc.retry_after,
                    ) from exc
                wait = compute_backoff_seconds(
                    attempt,
                    base=base,
                    maximum=maximum,
                    retry_after=exc.retry_after,
                )
                notice = format_retry_notice(attempt + 1, max_retries, wait)
                logger.warning(
                    "%s stream rate-limited, retry %s/%s in %.1fs",
                    self.name,
                    attempt + 1,
                    max_retries,
                    wait,
                )
                yield ModelChunk(
                    content="",
                    notice=notice,
                    retry_attempt=attempt + 1,
                    retry_wait_seconds=wait,
                    raw={"rate_limited": True},
                )
                await asyncio.sleep(wait)
                attempt += 1

    async def _stream_once(self, request: ModelRequest) -> AsyncIterator[ModelChunk]:
        url = f"{self.base_url}/chat/completions"
        payload = self._payload(request, stream=True)
        timeout = self.settings.model_timeout_seconds
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", url, headers=self._headers(), json=payload) as resp:
                if resp.status_code >= 400:
                    body = await resp.aread()
                    text = body.decode("utf-8", errors="ignore")
                    raise_if_rate_limited(resp.status_code, text, dict(resp.headers))
                    raise ModelGatewayError(
                        f"{self.name} stream HTTP {resp.status_code}: {text}"
                    )
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    if line.startswith("data:"):
                        line = line[5:].strip()
                    if line == "[DONE]":
                        yield ModelChunk(content="", finish_reason="stop")
                        break
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    # Some gateways embed error objects in SSE
                    if isinstance(data, dict) and data.get("error"):
                        err = data["error"]
                        msg = err if isinstance(err, str) else json.dumps(err, ensure_ascii=False)
                        raise_if_rate_limited(429 if "1305" in msg or "429" in msg else 500, msg)
                        raise ModelGatewayError(f"{self.name} stream error: {msg}")
                    choice = (data.get("choices") or [{}])[0]
                    delta = choice.get("delta") or {}
                    yield ModelChunk(
                        content=delta.get("content") or "",
                        finish_reason=choice.get("finish_reason"),
                        tool_calls=delta.get("tool_calls"),
                        usage=data.get("usage"),
                        raw=data,
                    )

    @staticmethod
    def _echo_fallback(request: ModelRequest) -> str:
        last_user = ""
        for m in reversed(request.messages):
            if m.role == ChatRole.USER:
                last_user = m.content
                break
        return (
            "[Nexus-Lark-Mind demo mode] No API key configured for this provider. "
            f"Echo: {last_user}"
        )
