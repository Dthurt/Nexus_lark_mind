"""Experimental agent team mailbox with durable KV + optional file fallback.

Enable with ``NLM_EXPERIMENTAL_TEAMS=true``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_TTL = 7 * 86400


@dataclass
class TeamMessage:
    id: str
    team_id: str
    from_id: str
    to_id: str  # agent id or "*" for broadcast
    payload: Dict[str, Any]
    created_at: float = field(default_factory=time.time)
    claimed_by: Optional[str] = None
    claimed_at: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TeamMessage":
        return cls(
            id=str(data.get("id") or ""),
            team_id=str(data.get("team_id") or ""),
            from_id=str(data.get("from_id") or ""),
            to_id=str(data.get("to_id") or "*"),
            payload=dict(data.get("payload") or {}),
            created_at=float(data.get("created_at") or time.time()),
            claimed_by=data.get("claimed_by"),
            claimed_at=data.get("claimed_at"),
        )


def _mbox_key(team_id: str) -> str:
    return f"team:mbox:{team_id}"


def _file_path(team_id: str) -> Path:
    root = Path("data") / "teams"
    root.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in team_id)[:80]
    return root / f"{safe}.json"


async def _broker():
    from src.infrastructure.redis_client import create_broker

    return create_broker()


class TeamMailbox:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._boxes: Dict[str, List[TeamMessage]] = {}
        self._hydrated: set[str] = set()

    def _ensure_hydrated(self, team_id: str) -> None:
        if team_id in self._hydrated:
            return
        # Sync file hydrate first (works without event loop)
        path = _file_path(team_id)
        if path.is_file():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                msgs = [TeamMessage.from_dict(m) for m in (raw.get("messages") or []) if isinstance(m, dict)]
                with self._lock:
                    if team_id not in self._boxes:
                        self._boxes[team_id] = msgs
                self._hydrated.add(team_id)
                return
            except Exception:
                logger.debug("team mailbox file hydrate failed for %s", team_id, exc_info=True)
        # Best-effort async KV hydrate if a loop is running
        try:
            loop = asyncio.get_running_loop()

            async def _kv() -> None:
                try:
                    broker = await _broker()
                    data = await broker.kv_get(_mbox_key(team_id))
                    if not data:
                        return
                    msgs = [
                        TeamMessage.from_dict(m)
                        for m in (data.get("messages") or [])
                        if isinstance(m, dict)
                    ]
                    with self._lock:
                        if team_id not in self._boxes or not self._boxes[team_id]:
                            self._boxes[team_id] = msgs
                    self._hydrated.add(team_id)
                except Exception:
                    logger.debug("team mailbox kv hydrate failed for %s", team_id, exc_info=True)

            loop.create_task(_kv())
        except RuntimeError:
            pass
        self._hydrated.add(team_id)

    def _persist(self, team_id: str) -> None:
        with self._lock:
            msgs = [m.to_dict() for m in self._boxes.get(team_id, [])]
        payload = {"messages": msgs, "updated_at": time.time()}
        try:
            _file_path(team_id).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        except Exception:
            logger.debug("team mailbox file persist failed for %s", team_id, exc_info=True)
        try:
            loop = asyncio.get_running_loop()

            async def _kv() -> None:
                try:
                    broker = await _broker()
                    await broker.kv_set(_mbox_key(team_id), payload, ttl=_TTL)
                except Exception:
                    logger.debug("team mailbox kv persist failed for %s", team_id, exc_info=True)

            loop.create_task(_kv())
        except RuntimeError:
            pass

    def post(
        self,
        team_id: str,
        *,
        from_id: str,
        to_id: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> TeamMessage:
        self._ensure_hydrated(team_id)
        msg = TeamMessage(
            id=f"tm_{uuid.uuid4().hex[:12]}",
            team_id=team_id,
            from_id=from_id,
            to_id=to_id or "*",
            payload=dict(payload or {}),
        )
        with self._lock:
            self._boxes.setdefault(team_id, []).append(msg)
            box = self._boxes[team_id]
            if len(box) > 200:
                del box[: len(box) - 200]
        self._persist(team_id)
        return msg

    def claim(
        self,
        team_id: str,
        agent_id: str,
        *,
        max_n: int = 8,
    ) -> List[TeamMessage]:
        self._ensure_hydrated(team_id)
        out: List[TeamMessage] = []
        with self._lock:
            for msg in self._boxes.get(team_id, []):
                if msg.claimed_by:
                    continue
                if msg.to_id not in {"*", agent_id}:
                    continue
                msg.claimed_by = agent_id
                msg.claimed_at = time.time()
                out.append(msg)
                if len(out) >= max_n:
                    break
        if out:
            self._persist(team_id)
        return out

    def list_all(self, team_id: str) -> List[TeamMessage]:
        self._ensure_hydrated(team_id)
        with self._lock:
            return list(self._boxes.get(team_id, []))

    def list_pending(self, team_id: str, agent_id: Optional[str] = None) -> List[TeamMessage]:
        self._ensure_hydrated(team_id)
        with self._lock:
            msgs = list(self._boxes.get(team_id, []))
        if agent_id:
            msgs = [m for m in msgs if not m.claimed_by and m.to_id in {"*", agent_id}]
        else:
            msgs = [m for m in msgs if not m.claimed_by]
        return msgs

    def clear(self, team_id: str) -> int:
        with self._lock:
            n = len(self._boxes.pop(team_id, []) or [])
        self._hydrated.discard(team_id)
        try:
            _file_path(team_id).unlink(missing_ok=True)  # type: ignore[arg-type]
        except TypeError:
            p = _file_path(team_id)
            if p.exists():
                p.unlink()
        except Exception:
            pass
        try:
            loop = asyncio.get_running_loop()

            async def _kv() -> None:
                try:
                    broker = await _broker()
                    await broker.kv_delete(_mbox_key(team_id))
                except Exception:
                    pass

            loop.create_task(_kv())
        except RuntimeError:
            pass
        return n

    def snapshot(self, team_id: str) -> Dict[str, Any]:
        msgs = self.list_all(team_id)
        agents: Dict[str, int] = {}
        for m in msgs:
            agents[m.from_id] = agents.get(m.from_id, 0) + 1
            if m.to_id != "*":
                agents.setdefault(m.to_id, 0)
        return {
            "team_id": team_id,
            "message_count": len(msgs),
            "pending": len([m for m in msgs if not m.claimed_by]),
            "agents": [{"id": k, "posts": v} for k, v in sorted(agents.items())],
            "messages": [m.to_dict() for m in msgs[-40:]],
        }


_MAILBOX: Optional[TeamMailbox] = None
_LOCK = threading.Lock()


def get_team_mailbox() -> TeamMailbox:
    global _MAILBOX
    with _LOCK:
        if _MAILBOX is None:
            _MAILBOX = TeamMailbox()
        return _MAILBOX
