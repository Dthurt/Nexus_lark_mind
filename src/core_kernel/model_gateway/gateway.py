"""Model Gateway facade — unified complete / stream with audit logging."""

from __future__ import annotations

import time
from typing import AsyncIterator, Optional

from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from src.common.config import Settings, get_settings
from src.common.schemas import ModelChunk, ModelRequest, ModelResponse
from src.core_kernel.model_gateway.registry import ProviderRegistry
from src.infrastructure.storage.repositories import ModelCallRepository


class ModelGateway:
    def __init__(
        self,
        settings: Optional[Settings] = None,
        session_factory: Optional[async_sessionmaker[AsyncSession]] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.registry = ProviderRegistry(self.settings)
        self.session_factory = session_factory

    async def complete(self, request: ModelRequest, *, task_id: Optional[str] = None) -> ModelResponse:
        provider_name = request.provider or self.settings.default_model_provider
        provider = self.registry.get(provider_name)
        if not request.model:
            model = getattr(provider, "default_model", None) or self.settings.default_model_name
            request = request.model_copy(update={"model": model})

        started = time.perf_counter()
        error: Optional[str] = None
        response: Optional[ModelResponse] = None
        try:
            response = await provider.guarded_complete(request)
            return response
        except Exception as exc:
            error = str(exc)
            raise
        finally:
            latency = (time.perf_counter() - started) * 1000
            await self._audit(
                request=request,
                provider_name=provider_name,
                response=response,
                error=error,
                latency_ms=latency,
                task_id=task_id,
            )

    async def stream(
        self,
        request: ModelRequest,
        *,
        task_id: Optional[str] = None,
    ) -> AsyncIterator[ModelChunk]:
        provider_name = request.provider or self.settings.default_model_provider
        provider = self.registry.get(provider_name)
        if not request.model:
            model = getattr(provider, "default_model", None) or self.settings.default_model_name
            request = request.model_copy(update={"model": model})

        started = time.perf_counter()
        collected = ""
        error: Optional[str] = None
        finish_reason: Optional[str] = None
        usage: dict = {}
        try:
            async for chunk in provider.guarded_stream(request):
                collected += chunk.content or ""
                if chunk.finish_reason:
                    finish_reason = chunk.finish_reason
                if chunk.usage:
                    usage = dict(chunk.usage)
                yield chunk
        except Exception as exc:
            error = str(exc)
            raise
        finally:
            latency = (time.perf_counter() - started) * 1000
            response = ModelResponse(
                content=collected,
                finish_reason=finish_reason,
                usage=usage,
                provider=provider_name,
                model=request.model or self.settings.default_model_name,
            )
            await self._audit(
                request=request,
                provider_name=provider_name,
                response=response if error is None else None,
                error=error,
                latency_ms=latency,
                task_id=task_id,
            )

    async def _audit(
        self,
        *,
        request: ModelRequest,
        provider_name: str,
        response: Optional[ModelResponse],
        error: Optional[str],
        latency_ms: float,
        task_id: Optional[str],
    ) -> None:
        if self.session_factory is None:
            return
        async with self.session_factory() as session:
            repo = ModelCallRepository(session)
            usage = (response.usage if response else {}) or {}
            await repo.record(
                provider=provider_name,
                model=request.model or self.settings.default_model_name,
                request=request.model_dump(mode="json"),
                response=response.model_dump(mode="json") if response else None,
                success=error is None,
                error=error,
                latency_ms=latency_ms,
                prompt_tokens=int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0),
                completion_tokens=int(
                    usage.get("completion_tokens") or usage.get("output_tokens") or 0
                ),
                task_id=task_id,
            )
            await session.commit()
