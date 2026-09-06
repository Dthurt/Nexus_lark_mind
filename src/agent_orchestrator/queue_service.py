"""Task queue service — Redis-backed enqueue / dequeue."""

from __future__ import annotations

import logging
from typing import Optional

from src.common.errors import QueueError
from src.common.schemas import StandardTask, TaskStatus
from src.infrastructure.redis_client import RedisClient

logger = logging.getLogger(__name__)


class QueueService:
    def __init__(self, redis_client: RedisClient) -> None:
        self.redis = redis_client

    async def enqueue(self, task: StandardTask) -> StandardTask:
        task.status = TaskStatus.QUEUED
        try:
            await self.redis.enqueue_task(task)
        except Exception as exc:
            raise QueueError(f"failed to enqueue task {task.task_id}: {exc}") from exc
        logger.info("Enqueued task %s channel=%s", task.task_id, task.channel.value)
        return task

    async def dequeue(self, timeout: int = 5) -> Optional[StandardTask]:
        return await self.redis.dequeue_task(timeout=timeout)
