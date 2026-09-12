"""Subagent backend protocol + in-process default (ACP multi-backend hook)."""

from __future__ import annotations

from typing import Any, AsyncIterator, Dict, Optional, Protocol, runtime_checkable


@runtime_checkable
class SubagentBackend(Protocol):
    """Minimal multi-backend contract."""

    name: str

    async def spawn(
        self,
        *,
        prompt: str,
        session_id: str,
        cwd: Optional[str] = None,
        model: Optional[str] = None,
        label: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a child agent handle. Returns public record with at least ``id``."""
        ...

    async def describe(self, agent_id: str) -> Optional[Dict[str, Any]]:
        ...


class InProcessBackend:
    """Registers a child on the existing SubagentRegistry (same process as parent)."""

    name = "inprocess"

    async def spawn(
        self,
        *,
        prompt: str,
        session_id: str,
        cwd: Optional[str] = None,
        model: Optional[str] = None,
        label: Optional[str] = None,
    ) -> Dict[str, Any]:
        from src.common.schemas import ChatMessage, ChatRole
        from src.core_kernel.subagent.registry import get_subagent_registry

        reg = get_subagent_registry()
        rec = reg.create(
            label=label or "backend-child",
            mode="spawn",
            parent_session_id=session_id,
            parent_task_id="acp",
            parent_call_id="acp",
            depth=1,
            provider=None,
            model=model,
            workspace_cwd=cwd,
            workspace_meta={},
            seed_messages=[ChatMessage(role=ChatRole.USER, content=prompt)],
        )
        await reg.persist(rec)
        out = rec.public()
        out["backend"] = self.name
        out["prompt_preview"] = (prompt or "")[:200]
        return out

    async def describe(self, agent_id: str) -> Optional[Dict[str, Any]]:
        from src.core_kernel.subagent.registry import get_subagent_registry

        reg = get_subagent_registry()
        rec = reg.get(agent_id) or await reg.hydrate(agent_id)
        if not rec:
            return None
        out = rec.public()
        out["backend"] = self.name
        return out


_BACKENDS: Dict[str, SubagentBackend] = {}


def get_subagent_backend(name: str = "inprocess") -> SubagentBackend:
    key = (name or "inprocess").strip().lower() or "inprocess"
    if key not in _BACKENDS:
        if key == "inprocess":
            _BACKENDS[key] = InProcessBackend()
        else:
            raise KeyError(f"unknown subagent backend: {key}")
    return _BACKENDS[key]


def list_subagent_backends() -> list[str]:
    get_subagent_backend("inprocess")
    return sorted(_BACKENDS.keys())
