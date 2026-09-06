"""Session context helpers via Redis (no direct DB access)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.common.schemas import ChatMessage
from src.infrastructure.redis_client import RedisClient


class SessionContext:
    def __init__(self, redis_client: RedisClient) -> None:
        self.redis = redis_client

    async def load_messages(self, session_id: str) -> List[Dict[str, Any]]:
        session = await self.redis.get_session(session_id)
        if not session:
            return []
        return list(session.get("messages") or [])

    async def append(self, session_id: str, message: ChatMessage) -> Dict[str, Any]:
        return await self.redis.append_session_message(
            session_id,
            message.model_dump(mode="json"),
        )

    async def ensure(self, session_id: str, *, user_id: str, channel: str) -> Dict[str, Any]:
        existing = await self.redis.get_session(session_id)
        if existing:
            return existing
        payload = {
            "session_id": session_id,
            "user_id": user_id,
            "channel": channel,
            "messages": [],
        }
        await self.redis.set_session(session_id, payload)
        return payload
