"""Unified exception hierarchy — catch at boundaries, re-raise as typed errors."""

from typing import Any, Optional


class NexusError(Exception):
    """Base error for all Nexus-Lark-Mind failures."""

    code: str = "NEXUS_ERROR"
    status_code: int = 500

    def __init__(self, message: str, *, detail: Optional[Any] = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail

    def to_dict(self) -> dict:
        payload = {"code": self.code, "message": self.message}
        if self.detail is not None:
            payload["detail"] = self.detail
        return payload


class ValidationAppError(NexusError):
    code = "VALIDATION_ERROR"
    status_code = 400


class NotFoundError(NexusError):
    code = "NOT_FOUND"
    status_code = 404


class AuthError(NexusError):
    code = "AUTH_ERROR"
    status_code = 401


class UpstreamError(NexusError):
    code = "UPSTREAM_ERROR"
    status_code = 502


class ModelGatewayError(NexusError):
    code = "MODEL_GATEWAY_ERROR"
    status_code = 502


class CircuitOpenError(ModelGatewayError):
    code = "CIRCUIT_OPEN"
    status_code = 503


class RateLimitError(ModelGatewayError):
    """Upstream model returned 429 / rate limited — eligible for backoff retry."""

    code = "RATE_LIMITED"
    status_code = 429

    def __init__(
        self,
        message: str,
        *,
        detail=None,
        retry_after: Optional[float] = None,
        status_code: int = 429,
    ) -> None:
        super().__init__(message, detail=detail)
        self.retry_after = retry_after
        self.status_code = status_code


class PluginError(NexusError):
    code = "PLUGIN_ERROR"
    status_code = 500


class PluginIsolatedCrash(PluginError):
    code = "PLUGIN_CRASH"
    status_code = 500


class StorageError(NexusError):
    code = "STORAGE_ERROR"
    status_code = 500


class QueueError(NexusError):
    code = "QUEUE_ERROR"
    status_code = 500


class RpcError(NexusError):
    code = "RPC_ERROR"
    status_code = 502
