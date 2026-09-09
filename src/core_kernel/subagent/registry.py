"""In-process subagent registry — spawn / fork / continuable children."""

from __future__ import annotations

import asyncio
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.common.schemas import ChatMessage


@dataclass
class SubagentRecord:
    id: str
    label: str
    mode: str  # spawn | fork
    parent_session_id: str
    parent_task_id: str
    parent_call_id: str
    depth: int
    status: str = "running"  # running | idle | ready | interrupted | failed
    provider: Optional[str] = None
    model: Optional[str] = None
    workspace_cwd: Optional[str] = None
    workspace_meta: Optional[Dict[str, Any]] = None
    messages: List[ChatMessage] = field(default_factory=list)
    transcript: List[Dict[str, Any]] = field(default_factory=list)
    final_output: str = ""
    error: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)

    def public(self) -> Dict[str, Any]:
        return {
            "kind": "child",
            "id": self.id,
            "label": self.label,
            "mode": self.mode,
            "status": self.status,
            "depth": self.depth,
            "parent_session_id": self.parent_session_id,
            "final_output": (self.final_output or "")[:500],
            "error": self.error or None,
        }


class SubagentRegistry:
    def __init__(self) -> None:
        self._agents: Dict[str, SubagentRecord] = {}
        self._lock = threading.RLock()

    def create(
        self,
        *,
        label: str,
        mode: str,
        parent_session_id: str,
        parent_task_id: str,
        parent_call_id: str,
        depth: int,
        provider: Optional[str],
        model: Optional[str],
        workspace_cwd: Optional[str],
        workspace_meta: Optional[Dict[str, Any]],
        seed_messages: Optional[List[ChatMessage]] = None,
    ) -> SubagentRecord:
        aid = f"sa_{uuid.uuid4().hex[:12]}"
        rec = SubagentRecord(
            id=aid,
            label=(label or "subagent").strip()[:80] or "subagent",
            mode=mode,
            parent_session_id=parent_session_id,
            parent_task_id=parent_task_id,
            parent_call_id=parent_call_id,
            depth=depth,
            provider=provider,
            model=model,
            workspace_cwd=workspace_cwd,
            workspace_meta=dict(workspace_meta or {}),
            messages=list(seed_messages or []),
        )
        with self._lock:
            self._agents[aid] = rec
        return rec

    def get(self, agent_id: str) -> Optional[SubagentRecord]:
        with self._lock:
            return self._agents.get(agent_id)

    def list_for_session(self, session_id: str, *, descendants: bool = False) -> List[SubagentRecord]:
        with self._lock:
            kids = [a for a in self._agents.values() if a.parent_session_id == session_id]
        if not descendants:
            return sorted(kids, key=lambda a: a.created_at)
        # For now all agents are direct children of a chat session; return same list.
        return sorted(kids, key=lambda a: a.created_at)

    def interrupt(self, agent_id: str) -> bool:
        rec = self.get(agent_id)
        if not rec:
            return False
        rec.cancel_event.set()
        if rec.status == "running":
            rec.status = "interrupted"
            rec.updated_at = time.time()
        return True


_registry: Optional[SubagentRegistry] = None
_reg_lock = threading.Lock()


def get_subagent_registry() -> SubagentRegistry:
    global _registry
    with _reg_lock:
        if _registry is None:
            _registry = SubagentRegistry()
        return _registry
