"""Anthropic Messages API provider (text + tools)."""

from __future__ import annotations

import json
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

from src.common.config import Settings
from src.common.errors import ModelGatewayError
from src.common.schemas import ChatMessage, ChatRole, ModelChunk, ModelRequest, ModelResponse
from src.core_kernel.model_gateway.base import BaseModelProvider


def _openai_tools_to_anthropic(tools: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for t in tools or []:
        if not isinstance(t, dict):
            continue
        fn = t.get("function") if t.get("type") == "function" else t
        if not isinstance(fn, dict):
            continue
        name = str(fn.get("name") or "").strip()
        if not name:
            continue
        params = fn.get("parameters") if isinstance(fn.get("parameters"), dict) else {"type": "object", "properties": {}}
        out.append(
            {
                "name": name,
                "description": str(fn.get("description") or "")[:1024],
                "input_schema": params,
            }
        )
    return out


class AnthropicProvider(BaseModelProvider):
    name = "anthropic"

    def __init__(
        self,
        settings: Optional[Settings] = None,
        *,
        name: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        default_model: Optional[str] = None,
    ) -> None:
        super().__init__(settings)
        if name:
            self.name = name
        self.api_key = api_key if api_key is not None else self.settings.anthropic_api_key
        self.base_url = (base_url or self.settings.anthropic_base_url).rstrip("/")
        self.default_model = (
            default_model
            or self.settings.anthropic_default_model
            or "claude-3-5-sonnet-20241022"
        )

    def _headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }

    def _split_messages(self, messages: List[ChatMessage]) -> tuple[Optional[str], List[Dict[str, Any]]]:
        from src.core_kernel.tool_history import sanitize_tool_call_messages

        messages = sanitize_tool_call_messages(messages)
        system_parts: List[str] = []
        converted: List[Dict[str, Any]] = []
        for m in messages:
            if m.role == ChatRole.SYSTEM:
                system_parts.append(m.content)
                continue
            if m.role == ChatRole.TOOL:
                converted.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": m.tool_call_id or m.name or "tool",
                                "content": m.content or "",
                            }
                        ],
                    }
                )
                continue
            if m.role == ChatRole.ASSISTANT:
                content: Any = m.content or ""
                tcs = (m.metadata or {}).get("tool_calls") if isinstance(m.metadata, dict) else None
                if tcs:
                    blocks: List[Dict[str, Any]] = []
                    if content:
                        blocks.append({"type": "text", "text": content})
                    for i, tc in enumerate(tcs):
                        if not isinstance(tc, dict):
                            continue
                        fn = tc.get("function") or {}
                        args = fn.get("arguments") if isinstance(fn, dict) else "{}"
                        if isinstance(args, dict):
                            inp = args
                        else:
                            try:
                                inp = json.loads(args or "{}")
                            except Exception:
                                inp = {}
                        blocks.append(
                            {
                                "type": "tool_use",
                                "id": tc.get("id") or f"toolu_{i}",
                                "name": (fn.get("name") if isinstance(fn, dict) else None) or "tool",
                                "input": inp if isinstance(inp, dict) else {},
                            }
                        )
                    converted.append({"role": "assistant", "content": blocks})
                else:
                    converted.append({"role": "assistant", "content": content})
                continue
            converted.append({"role": "user", "content": m.content})
        system = "\n".join(system_parts) if system_parts else None
        return system, converted

    def _payload(self, request: ModelRequest, *, stream: bool) -> Dict[str, Any]:
        system, msgs = self._split_messages(request.messages)
        payload: Dict[str, Any] = {
            "model": request.model or self.default_model,
            "messages": msgs,
            "max_tokens": request.max_tokens or 4096,
            "temperature": request.temperature,
            "stream": stream,
        }
        if system:
            payload["system"] = system
        tools = _openai_tools_to_anthropic(request.tools)
        if tools:
            payload["tools"] = tools
        # Soft map high reasoning → Anthropic extended thinking on models that advertise it.
        effort = str(getattr(request, "reasoning_effort", None) or "").strip().lower()
        model_l = str(payload.get("model") or "").lower()
        thinking_ok = any(
            k in model_l for k in ("claude-3-7", "claude-4", "sonnet-4", "opus-4", "thinking")
        )
        if effort == "high" and thinking_ok:
            budget = 8000
            max_tok = int(payload.get("max_tokens") or 4096)
            if max_tok <= budget:
                payload["max_tokens"] = budget + 2048
            payload["thinking"] = {"type": "enabled", "budget_tokens": budget}
        return payload

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

        payload = self._payload(request, stream=False)
        url = f"{self.base_url}/v1/messages"
        async with httpx.AsyncClient(timeout=self.settings.model_timeout_seconds) as client:
            resp = await client.post(url, headers=self._headers(), json=payload)
            if resp.status_code >= 400:
                raise ModelGatewayError(f"anthropic HTTP {resp.status_code}: {resp.text}")
            data = resp.json()

        content_blocks = data.get("content") or []
        text_parts: List[str] = []
        tool_calls: List[Dict[str, Any]] = []
        for i, b in enumerate(content_blocks):
            if not isinstance(b, dict):
                continue
            if b.get("type") == "text":
                text_parts.append(b.get("text") or "")
            elif b.get("type") == "tool_use":
                tool_calls.append(
                    {
                        "index": i,
                        "id": b.get("id") or f"toolu_{i}",
                        "type": "function",
                        "function": {
                            "name": b.get("name") or "",
                            "arguments": json.dumps(b.get("input") or {}, ensure_ascii=False),
                        },
                    }
                )
        usage = data.get("usage") or {}
        return ModelResponse(
            content="".join(text_parts),
            finish_reason=data.get("stop_reason"),
            tool_calls=tool_calls,
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

        payload = self._payload(request, stream=True)
        url = f"{self.base_url}/v1/messages"
        # Accumulate tool_use blocks across stream events
        tool_acc: Dict[int, Dict[str, Any]] = {}
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
                    if etype == "content_block_start":
                        block = data.get("content_block") or {}
                        idx = int(data.get("index") or 0)
                        if block.get("type") == "tool_use":
                            tool_acc[idx] = {
                                "index": idx,
                                "id": block.get("id") or f"toolu_{idx}",
                                "type": "function",
                                "function": {
                                    "name": block.get("name") or "",
                                    "arguments": "",
                                },
                            }
                            yield ModelChunk(
                                content="",
                                tool_calls=[
                                    {
                                        "index": idx,
                                        "id": tool_acc[idx]["id"],
                                        "type": "function",
                                        "function": {
                                            "name": tool_acc[idx]["function"]["name"],
                                            "arguments": "",
                                        },
                                    }
                                ],
                            )
                    elif etype == "content_block_delta":
                        delta = data.get("delta") or {}
                        idx = int(data.get("index") or 0)
                        if delta.get("type") == "text_delta":
                            yield ModelChunk(content=delta.get("text") or "")
                        elif delta.get("type") == "input_json_delta":
                            piece = delta.get("partial_json") or ""
                            if idx in tool_acc:
                                tool_acc[idx]["function"]["arguments"] += piece
                            yield ModelChunk(
                                content="",
                                tool_calls=[
                                    {
                                        "index": idx,
                                        "id": (tool_acc.get(idx) or {}).get("id"),
                                        "type": "function",
                                        "function": {"arguments": piece},
                                    }
                                ],
                            )
                    elif etype == "message_delta":
                        delta = data.get("delta") or {}
                        stop = delta.get("stop_reason")
                        if stop:
                            yield ModelChunk(content="", finish_reason=stop)
                    elif etype == "message_stop":
                        yield ModelChunk(content="", finish_reason="end_turn")
