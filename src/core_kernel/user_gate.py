"""In-process user gates for tool approval / ask_user (resolved via Kernel RPC)."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# call_id -> Future
_FUTURES: Dict[str, asyncio.Future] = {}
# call_id -> {session_id, kind, created_at, meta}
_META: Dict[str, Dict[str, Any]] = {}
_LOCK = asyncio.Lock()


async def open_gate(
    call_id: str,
    *,
    session_id: str,
    kind: str,
    meta: Optional[Dict[str, Any]] = None,
) -> None:
    """Register a pending gate before awaiting."""
    async with _LOCK:
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        old = _FUTURES.pop(call_id, None)
        if old and not old.done():
            old.set_result({"action": "deny", "reason": "superseded"})
        _FUTURES[call_id] = fut
        _META[call_id] = {
            "session_id": session_id or "",
            "kind": kind,
            "created_at": time.time(),
            "meta": meta or {},
        }


async def await_gate(call_id: str, *, timeout: float = 600.0) -> Dict[str, Any]:
    """Block until resolve_gate / deny / timeout."""
    fut = _FUTURES.get(call_id)
    if fut is None:
        return {"action": "deny", "reason": "unknown_gate"}
    try:
        result = await asyncio.wait_for(asyncio.shield(fut), timeout=timeout)
        if isinstance(result, dict):
            return result
        return {"action": "deny", "reason": "invalid_result"}
    except asyncio.TimeoutError:
        await resolve_gate(call_id, {"action": "deny", "reason": "timeout"})
        return {"action": "deny", "reason": "timeout"}
    finally:
        async with _LOCK:
            _FUTURES.pop(call_id, None)
            _META.pop(call_id, None)


async def resolve_gate(call_id: str, payload: Dict[str, Any]) -> bool:
    """Resolve a pending gate (called from RPC)."""
    async with _LOCK:
        fut = _FUTURES.get(call_id)
        if fut is None or fut.done():
            return False
        fut.set_result(payload if isinstance(payload, dict) else {"action": "deny"})
        return True


async def deny_session_gates(session_id: str, reason: str = "cancelled") -> int:
    """Deny all open gates for a session (cancel / stop)."""
    async with _LOCK:
        ids = [cid for cid, m in _META.items() if m.get("session_id") == session_id]
    n = 0
    for cid in ids:
        ok = await resolve_gate(cid, {"action": "deny", "reason": reason})
        if ok:
            n += 1
    return n


def list_session_gates(session_id: str) -> List[Dict[str, Any]]:
    out = []
    for cid, m in list(_META.items()):
        if m.get("session_id") == session_id:
            out.append({"call_id": cid, **m})
    return out
