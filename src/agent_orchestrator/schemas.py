"""Orchestrator-local schemas."""

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from src.common.schemas import StandardTask


class EnqueueRequest(BaseModel):
    task: StandardTask


class EnqueueResponse(BaseModel):
    task_id: str
    session_id: str
    status: str = "queued"


class DispatchResult(BaseModel):
    task_id: str
    session_id: str
    ok: bool
    content: Optional[str] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
