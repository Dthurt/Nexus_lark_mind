"""Cross-layer standard task / event / RPC schemas (Pydantic V2)."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str = "") -> str:
    uid = uuid4().hex
    return f"{prefix}{uid}" if prefix else uid


class ChannelType(str, Enum):
    FEISHU = "feishu"
    WEB = "web"
    SYSTEM = "system"


class TaskStatus(str, Enum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    STREAMING = "streaming"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class EventType(str, Enum):
    TASK_CREATED = "task.created"
    TASK_STARTED = "task.started"
    TASK_DELTA = "task.delta"
    TASK_STATUS = "task.status"
    TASK_TOOL_CALL = "task.tool_call"
    TASK_TOOL_RESULT = "task.tool_result"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    SESSION_UPDATED = "session.updated"


class ChatRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ChatMessage(BaseModel):
    role: ChatRole
    content: str
    name: Optional[str] = None
    tool_call_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class StandardTask(BaseModel):
    """Canonical inbound task — adapters normalize everything into this."""

    task_id: str = Field(default_factory=lambda: new_id("task_"))
    session_id: str = Field(default_factory=lambda: new_id("sess_"))
    channel: ChannelType
    user_id: str
    content: str
    messages: List[ChatMessage] = Field(default_factory=list)
    model_provider: Optional[str] = None
    model_name: Optional[str] = None
    tools_enabled: bool = True
    stream: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)
    status: TaskStatus = TaskStatus.PENDING


class StreamDelta(BaseModel):
    task_id: str
    session_id: str
    delta: str = ""
    done: bool = False
    event_type: EventType = EventType.TASK_DELTA
    tool_name: Optional[str] = None
    tool_payload: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    ts: datetime = Field(default_factory=utcnow)


class BusEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: new_id("evt_"))
    event_type: EventType
    task_id: str
    session_id: str
    channel: ChannelType
    payload: Dict[str, Any] = Field(default_factory=dict)
    ts: datetime = Field(default_factory=utcnow)


class ModelRequest(BaseModel):
    provider: Optional[str] = None
    model: Optional[str] = None
    messages: List[ChatMessage]
    tools: Optional[List[Dict[str, Any]]] = None
    stream: bool = True
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ModelChunk(BaseModel):
    content: str = ""
    finish_reason: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    usage: Optional[Dict[str, Any]] = None
    raw: Optional[Dict[str, Any]] = None
    # User-facing status (e.g. rate-limit backoff notice); not model text
    notice: Optional[str] = None
    retry_attempt: Optional[int] = None
    retry_wait_seconds: Optional[float] = None


class ModelResponse(BaseModel):
    content: str = ""
    finish_reason: Optional[str] = None
    tool_calls: List[Dict[str, Any]] = Field(default_factory=list)
    usage: Dict[str, Any] = Field(default_factory=dict)
    provider: str = ""
    model: str = ""


class PluginInvokeRequest(BaseModel):
    plugin_id: str
    tool_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: float = 60.0


class PluginInvokeResult(BaseModel):
    plugin_id: str
    tool_name: str
    success: bool
    result: Any = None
    error: Optional[str] = None
    duration_ms: float = 0.0


class RpcEnvelope(BaseModel):
    ok: bool = True
    data: Any = None
    error: Optional[Dict[str, Any]] = None
