"""Lightweight HTTP RPC client used by adapters / orchestrator → kernel."""

from typing import Any, AsyncIterator, Dict, Optional

import httpx
import orjson

from src.common.errors import RpcError
from src.common.schemas import RpcEnvelope


class RpcClient:
    def __init__(
        self,
        base_url: str,
        timeout: float = 120.0,
        stream_timeout: float = 600.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.stream_timeout = stream_timeout
        self._client: Optional[httpx.AsyncClient] = None
        self._stream_client: Optional[httpx.AsyncClient] = None

    async def start(self) -> None:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout),
            )
        if self._stream_client is None:
            self._stream_client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(
                    connect=15.0,
                    read=self.stream_timeout,
                    write=30.0,
                    pool=15.0,
                ),
            )

    async def stop(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        if self._stream_client is not None:
            await self._stream_client.aclose()
            self._stream_client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RpcError("RPC client not started")
        return self._client

    @property
    def stream_client(self) -> httpx.AsyncClient:
        if self._stream_client is None:
            raise RpcError("RPC stream client not started")
        return self._stream_client

    async def call(
        self,
        method: str,
        path: str,
        *,
        json: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Any:
        try:
            response = await self.client.request(method, path, json=json, params=params)
        except httpx.HTTPError as exc:
            raise RpcError(f"RPC transport failure: {exc}") from exc

        if response.status_code >= 400:
            try:
                body = response.json()
            except Exception:
                body = {"message": response.text}
            inner = body.get("error") if isinstance(body, dict) else None
            if isinstance(inner, dict) and inner.get("message"):
                raise RpcError(str(inner["message"]), detail=body)
            if isinstance(body, dict) and body.get("message"):
                raise RpcError(str(body["message"]), detail=body)
            raise RpcError(
                f"RPC {method} {path} failed ({response.status_code})",
                detail=body,
            )

        payload = response.json()
        envelope = RpcEnvelope.model_validate(payload)
        if not envelope.ok:
            err = envelope.error or {}
            msg = err.get("message") if isinstance(err, dict) else str(err or "")
            raise RpcError(msg or "RPC logical failure", detail=err)
        return envelope.data

    async def stream_post(
        self,
        path: str,
        json: Dict[str, Any],
        *,
        abort_event: Optional[Any] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        try:
            async with self.stream_client.stream("POST", path, json=json) as response:
                if response.status_code >= 400:
                    text = await response.aread()
                    raise RpcError(
                        f"RPC stream failed ({response.status_code})",
                        detail=text.decode("utf-8", errors="ignore"),
                    )
                async for line in response.aiter_lines():
                    if abort_event is not None and getattr(abort_event, "is_set", lambda: False)():
                        await response.aclose()
                        yield {"delta": "", "done": True, "error": "cancelled", "cancelled": True}
                        return
                    if not line:
                        continue
                    # SSE comment / keepalive lines
                    if line.startswith(":"):
                        continue
                    if line.startswith("data:"):
                        line = line[5:].strip()
                    if line == "[DONE]":
                        break
                    try:
                        yield orjson.loads(line)
                    except orjson.JSONDecodeError:
                        continue
        except httpx.HTTPError as exc:
            raise RpcError(f"RPC stream transport failure: {exc}") from exc
