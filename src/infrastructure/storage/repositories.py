"""Repository helpers — used exclusively by Core Kernel."""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.common.schemas import new_id
from src.infrastructure.storage.models import (
    ModelCallRecord,
    PluginCallRecord,
    SessionRecord,
    SystemLogRecord,
    TaskRecord,
)


class TaskRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert_task(
        self,
        *,
        task_id: str,
        session_id: str,
        channel: str,
        user_id: str,
        content: str,
        status: str,
        model_provider: Optional[str] = None,
        model_name: Optional[str] = None,
        result_text: Optional[str] = None,
        error: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> TaskRecord:
        result = await self.session.execute(select(TaskRecord).where(TaskRecord.task_id == task_id))
        row = result.scalar_one_or_none()
        if row is None:
            row = TaskRecord(
                task_id=task_id,
                session_id=session_id,
                channel=channel,
                user_id=user_id,
                content=content,
                status=status,
                model_provider=model_provider,
                model_name=model_name,
                result_text=result_text,
                error=error,
                metadata_json=metadata or {},
            )
            self.session.add(row)
        else:
            row.status = status
            if model_provider is not None:
                row.model_provider = model_provider
            if model_name is not None:
                row.model_name = model_name
            if result_text is not None:
                row.result_text = result_text
            if error is not None:
                row.error = error
            if metadata is not None:
                row.metadata_json = metadata
        await self.session.flush()
        return row

    async def get(self, task_id: str) -> Optional[TaskRecord]:
        result = await self.session.execute(select(TaskRecord).where(TaskRecord.task_id == task_id))
        return result.scalar_one_or_none()


class SessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_or_create(
        self,
        session_id: str,
        *,
        channel: str,
        user_id: str,
    ) -> SessionRecord:
        result = await self.session.execute(
            select(SessionRecord).where(SessionRecord.session_id == session_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            row = SessionRecord(
                session_id=session_id,
                channel=channel,
                user_id=user_id,
                messages_json=[],
                metadata_json={},
            )
            self.session.add(row)
            await self.session.flush()
        return row

    async def append_messages(self, session_id: str, messages: list[dict]) -> SessionRecord:
        result = await self.session.execute(
            select(SessionRecord).where(SessionRecord.session_id == session_id)
        )
        row = result.scalar_one()
        current = list(row.messages_json or [])
        current.extend(messages)
        row.messages_json = current
        await self.session.flush()
        return row


class PluginCallRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def record(
        self,
        *,
        plugin_id: str,
        tool_name: str,
        arguments: dict,
        success: bool,
        result: Any,
        error: Optional[str],
        duration_ms: float,
        task_id: Optional[str] = None,
    ) -> PluginCallRecord:
        row = PluginCallRecord(
            call_id=new_id("pcall_"),
            task_id=task_id,
            plugin_id=plugin_id,
            tool_name=tool_name,
            arguments_json=arguments,
            success=1 if success else 0,
            result_json={"value": result} if result is not None else None,
            error=error,
            duration_ms=duration_ms,
        )
        self.session.add(row)
        await self.session.flush()
        return row


class ModelCallRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def record(
        self,
        *,
        provider: str,
        model: str,
        request: dict,
        response: Optional[dict],
        success: bool,
        error: Optional[str],
        latency_ms: float,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        task_id: Optional[str] = None,
    ) -> ModelCallRecord:
        row = ModelCallRecord(
            call_id=new_id("mcall_"),
            task_id=task_id,
            provider=provider,
            model=model,
            request_json=request,
            response_json=response,
            success=1 if success else 0,
            error=error,
            latency_ms=latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
        self.session.add(row)
        await self.session.flush()
        return row


class LogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def write(
        self,
        *,
        level: str,
        service: str,
        message: str,
        context: Optional[dict] = None,
    ) -> SystemLogRecord:
        row = SystemLogRecord(
            level=level,
            service=service,
            message=message,
            context_json=context or {},
        )
        self.session.add(row)
        await self.session.flush()
        return row
