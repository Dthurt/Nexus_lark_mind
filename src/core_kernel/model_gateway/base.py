"""Abstract model provider interface + circuit breaker."""

from __future__ import annotations

import abc
import asyncio
import time
from typing import AsyncIterator, Optional

from src.common.config import Settings, get_settings
from src.common.errors import CircuitOpenError, ModelGatewayError, RateLimitError
from src.common.schemas import ModelChunk, ModelRequest, ModelResponse
from src.core_kernel.model_gateway.retry import format_rate_limit_exhausted, is_rate_limit_message


class CircuitBreaker:
    def __init__(self, failure_threshold: int, reset_seconds: float) -> None:
        self.failure_threshold = failure_threshold
        self.reset_seconds = reset_seconds
        self.failures = 0
        self.opened_at: Optional[float] = None
        self._lock = asyncio.Lock()

    async def before_call(self) -> None:
        async with self._lock:
            if self.opened_at is None:
                return
            if time.monotonic() - self.opened_at >= self.reset_seconds:
                self.opened_at = None
                self.failures = 0
                return
            raise CircuitOpenError("model provider circuit is open")

    async def record_success(self) -> None:
        async with self._lock:
            self.failures = 0
            self.opened_at = None

    async def record_failure(self) -> None:
        async with self._lock:
            self.failures += 1
            if self.failures >= self.failure_threshold:
                self.opened_at = time.monotonic()


class BaseModelProvider(abc.ABC):
    name: str

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        self.circuit = CircuitBreaker(
            failure_threshold=self.settings.model_circuit_failure_threshold,
            reset_seconds=float(self.settings.model_circuit_reset_seconds),
        )

    @abc.abstractmethod
    async def complete(self, request: ModelRequest) -> ModelResponse:
        raise NotImplementedError

    @abc.abstractmethod
    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelChunk]:
        raise NotImplementedError
        yield  # pragma: no cover — make this an async generator type

    async def guarded_complete(self, request: ModelRequest) -> ModelResponse:
        await self.circuit.before_call()
        try:
            result = await self.complete(request)
            await self.circuit.record_success()
            return result
        except CircuitOpenError:
            raise
        except RateLimitError as exc:
            # Exhausted retries — soft failure, do not trip circuit as hard outage
            await self.circuit.record_failure()
            raise RateLimitError(
                exc.message if is_rate_limit_message(exc.message) else format_rate_limit_exhausted(
                    self.settings.model_max_retries
                ),
                detail=exc.detail,
                retry_after=exc.retry_after,
            ) from exc
        except Exception as exc:
            await self.circuit.record_failure()
            raise ModelGatewayError(f"{self.name} complete failed: {exc}") from exc

    async def guarded_stream(self, request: ModelRequest) -> AsyncIterator[ModelChunk]:
        await self.circuit.before_call()
        try:
            async for chunk in self.stream(request):
                yield chunk
            await self.circuit.record_success()
        except CircuitOpenError:
            raise
        except RateLimitError as exc:
            await self.circuit.record_failure()
            raise RateLimitError(
                exc.message,
                detail=exc.detail,
                retry_after=exc.retry_after,
            ) from exc
        except Exception as exc:
            await self.circuit.record_failure()
            raise ModelGatewayError(f"{self.name} stream failed: {exc}") from exc
