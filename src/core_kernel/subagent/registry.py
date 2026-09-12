"""Subagent registry — spawn / fork / continuable children (memory + Redis/KV)."""

from __future__ import annotations

import asyncio
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.common.schemas import ChatMessage

logger = logging.getLogger(__name__)


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

    def to_persist(self) -> Dict[str, Any]:
        """Serialize for Redis/KV (no cancel_event)."""
        return {
            "id": self.id,
            "label": self.label,
            "mode": self.mode,
            "parent_session_id": self.parent_session_id,
            "parent_task_id": self.parent_task_id,
            "parent_call_id": self.parent_call_id,
            "depth": self.depth,
            "status": self.status if self.status != "running" else "idle",
            "provider": self.provider,
            "model": self.model,
            "workspace_cwd": self.workspace_cwd,
            "workspace_meta": dict(self.workspace_meta or {}),
            "messages": [m.model_dump(mode="json") for m in self.messages],
            "transcript": list(self.transcript or [])[-40:],
            "final_output": (self.final_output or "")[:8000],
            "error": self.error or "",
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_persist(cls, data: Dict[str, Any]) -> "SubagentRecord":
        msgs: List[ChatMessage] = []
        for raw in data.get("messages") or []:
            try:
                if isinstance(raw, ChatMessage):
                    msgs.append(raw)
                else:
                    msgs.append(ChatMessage.model_validate(raw))
            except Exception:
                continue
        status = str(data.get("status") or "idle")
        if status == "running":
            status = "idle"  # cannot resume mid-run after restart
        return cls(
            id=str(data.get("id") or ""),
            label=str(data.get("label") or "subagent"),
            mode=str(data.get("mode") or "spawn"),
            parent_session_id=str(data.get("parent_session_id") or ""),
            parent_task_id=str(data.get("parent_task_id") or ""),
            parent_call_id=str(data.get("parent_call_id") or ""),
            depth=int(data.get("depth") or 0),
            status=status,
            provider=data.get("provider"),
            model=data.get("model"),
            workspace_cwd=data.get("workspace_cwd"),
            workspace_meta=dict(data.get("workspace_meta") or {}),
            messages=msgs,
            transcript=list(data.get("transcript") or []),
            final_output=str(data.get("final_output") or ""),
            error=str(data.get("error") or ""),
            created_at=float(data.get("created_at") or time.time()),
            updated_at=float(data.get("updated_at") or time.time()),
            cancel_event=asyncio.Event(),
        )


def _agent_key(agent_id: str) -> str:
    return f"subagent:{agent_id}"


def _session_index_key(session_id: str) -> str:
    return f"subagents:sess:{session_id}"


async def _broker():
    from src.infrastructure.redis_client import create_broker

    broker = create_broker()
    await broker.connect()
    return broker


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

    async def persist(self, rec: SubagentRecord) -> None:
        """Write continuable snapshot to shared KV (best-effort)."""
        try:
            broker = await _broker()
            await broker.kv_set(_agent_key(rec.id), rec.to_persist(), ttl=7 * 86400)
            idx_key = _session_index_key(rec.parent_session_id)
            idx = await broker.kv_get(idx_key) or {"ids": []}
            ids = list(idx.get("ids") or [])
            if rec.id not in ids:
                ids.append(rec.id)
            # Cap index growth
            if len(ids) > 80:
                ids = ids[-80:]
            await broker.kv_set(idx_key, {"ids": ids}, ttl=7 * 86400)
        except Exception:
            logger.exception("subagent persist failed for %s", getattr(rec, "id", "?"))

    async def hydrate(self, agent_id: str) -> Optional[SubagentRecord]:
        """Load from memory, else KV (after process restart)."""
        existing = self.get(agent_id)
        if existing:
            return existing
        try:
            broker = await _broker()
            raw = await broker.kv_get(_agent_key(agent_id))
            if not raw:
                return None
            rec = SubagentRecord.from_persist(raw)
            if not rec.id:
                return None
            with self._lock:
                self._agents[rec.id] = rec
            return rec
        except Exception:
            logger.exception("subagent hydrate failed for %s", agent_id)
            return None

    async def list_for_session_async(
        self,
        session_id: str,
        *,
        descendants: bool = False,
    ) -> List[SubagentRecord]:
        """Merge in-memory agents with KV index for this session."""
        mem = {a.id: a for a in self.list_for_session(session_id, descendants=descendants)}
        try:
            broker = await _broker()
            idx = await broker.kv_get(_session_index_key(session_id)) or {}
            for aid in idx.get("ids") or []:
                aid = str(aid or "").strip()
                if not aid or aid in mem:
                    continue
                rec = await self.hydrate(aid)
                if rec and rec.parent_session_id == session_id:
                    mem[rec.id] = rec
        except Exception:
            logger.exception("subagent list hydrate failed for session %s", session_id)
        return sorted(mem.values(), key=lambda a: a.created_at)


_registry: Optional[SubagentRegistry] = None
_reg_lock = threading.Lock()


def get_subagent_registry() -> SubagentRegistry:
    global _registry
    with _reg_lock:
        if _registry is None:
            _registry = SubagentRegistry()
        return _registry
