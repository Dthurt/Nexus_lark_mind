"""User gates for tool approval / ask_user (in-process futures + Redis/KV mirror)."""

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


def _gate_key(call_id: str) -> str:
    return f"gate:{call_id}"


def _session_gates_key(session_id: str) -> str:
    return f"gates:sess:{session_id}"


async def _broker():
    from src.infrastructure.redis_client import create_broker

    broker = create_broker()
    await broker.connect()
    return broker


async def _mirror_open(call_id: str, meta: Dict[str, Any]) -> None:
    try:
        broker = await _broker()
        await broker.kv_set(_gate_key(call_id), meta, ttl=3600)
        sid = str(meta.get("session_id") or "")
        if sid:
            idx = await broker.kv_get(_session_gates_key(sid)) or {"ids": []}
            ids = [x for x in (idx.get("ids") or []) if x != call_id]
            ids.append(call_id)
            if len(ids) > 40:
                ids = ids[-40:]
            await broker.kv_set(_session_gates_key(sid), {"ids": ids}, ttl=3600)
    except Exception:
        logger.exception("gate mirror open failed for %s", call_id)


async def _mirror_clear(call_id: str, session_id: str = "") -> None:
    try:
        broker = await _broker()
        raw = await broker.kv_get(_gate_key(call_id))
        await broker.kv_delete(_gate_key(call_id))
        sid = session_id or (str((raw or {}).get("session_id") or "") if raw else "")
        if sid:
            idx = await broker.kv_get(_session_gates_key(sid)) or {"ids": []}
            ids = [x for x in (idx.get("ids") or []) if x != call_id]
            await broker.kv_set(_session_gates_key(sid), {"ids": ids}, ttl=3600)
    except Exception:
        logger.exception("gate mirror clear failed for %s", call_id)


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
        entry = {
            "session_id": session_id or "",
            "kind": kind,
            "created_at": time.time(),
            "meta": meta or {},
        }
        _META[call_id] = entry
    await _mirror_open(call_id, {"call_id": call_id, **entry})


async def await_gate(call_id: str, *, timeout: float = 600.0) -> Dict[str, Any]:
    """Block until resolve_gate / deny / timeout."""
    fut = _FUTURES.get(call_id)
    if fut is None:
        # Process restarted while a gate was open — deny cleanly.
        try:
            broker = await _broker()
            stale = await broker.kv_get(_gate_key(call_id))
            if stale:
                await _mirror_clear(call_id, str(stale.get("session_id") or ""))
                return {"action": "deny", "reason": "kernel_restart"}
        except Exception:
            pass
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
        sid = ""
        async with _LOCK:
            _FUTURES.pop(call_id, None)
            meta = _META.pop(call_id, None) or {}
            sid = str(meta.get("session_id") or "")
        await _mirror_clear(call_id, sid)


async def resolve_gate(call_id: str, payload: Dict[str, Any]) -> bool:
    """Resolve a pending gate (called from RPC)."""
    async with _LOCK:
        fut = _FUTURES.get(call_id)
        if fut is None or fut.done():
            # Clear orphaned mirror so UI does not keep a dead approval.
            pass
        else:
            fut.set_result(payload if isinstance(payload, dict) else {"action": "deny"})
            return True
    await _mirror_clear(call_id)
    return False


async def deny_session_gates(session_id: str, reason: str = "cancelled") -> int:
    """Deny all open gates for a session (cancel / stop)."""
    async with _LOCK:
        ids = [cid for cid, m in _META.items() if m.get("session_id") == session_id]
    # Also clear any mirrored orphans for this session.
    try:
        broker = await _broker()
        idx = await broker.kv_get(_session_gates_key(session_id)) or {}
        for cid in idx.get("ids") or []:
            if cid not in ids:
                ids.append(str(cid))
    except Exception:
        pass
    n = 0
    for cid in ids:
        ok = await resolve_gate(cid, {"action": "deny", "reason": reason})
        if ok:
            n += 1
        else:
            await _mirror_clear(cid, session_id)
    return n


def list_session_gates(session_id: str) -> List[Dict[str, Any]]:
    out = []
    for cid, m in list(_META.items()):
        if m.get("session_id") == session_id:
            out.append({"call_id": cid, **m})
    return out


async def list_session_gates_async(session_id: str) -> List[Dict[str, Any]]:
    """In-memory gates plus KV orphans (marked after kernel restart)."""
    out = {g["call_id"]: g for g in list_session_gates(session_id)}
    try:
        broker = await _broker()
        idx = await broker.kv_get(_session_gates_key(session_id)) or {}
        for cid in idx.get("ids") or []:
            cid = str(cid or "")
            if not cid or cid in out:
                continue
            raw = await broker.kv_get(_gate_key(cid))
            if not raw:
                continue
            out[cid] = {
                "call_id": cid,
                "session_id": session_id,
                "kind": raw.get("kind"),
                "created_at": raw.get("created_at"),
                "meta": raw.get("meta") or {},
                "orphaned": True,
                "reason": "kernel_restart",
            }
    except Exception:
        logger.exception("list_session_gates_async failed for %s", session_id)
    return list(out.values())


async def clear_orphaned_gates_on_startup() -> int:
    """Best-effort: mirrored gates without live futures cannot be answered — drop them."""
    # Without a global scan of all sessions we only clean when sessions interact.
    # This hook exists for symmetry / future index; currently a no-op count.
    return 0
