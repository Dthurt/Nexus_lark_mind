"""Base adapter contract."""

from __future__ import annotations

import abc
from typing import Any, Dict, Optional

from src.common.rpc_client import RpcClient
from src.common.schemas import ChannelType, StandardTask
from src.infrastructure.redis_client import RedisClient


class BaseAdapter(abc.ABC):
    channel: ChannelType

    def __init__(
        self,
        orchestrator: RpcClient,
        redis_client: RedisClient,
    ) -> None:
        self.orchestrator = orchestrator
        self.redis = redis_client

    async def submit(self, task: StandardTask) -> Dict[str, Any]:
        data = await self.orchestrator.call(
            "POST",
            "/rpc/tasks/enqueue",
            json={"task": task.model_dump(mode="json")},
        )
        return data

    @abc.abstractmethod
    async def handle_inbound(self, payload: Dict[str, Any]) -> Optional[StandardTask]:
        """Normalize raw external payload into StandardTask (or None to ignore)."""
        raise NotImplementedError
