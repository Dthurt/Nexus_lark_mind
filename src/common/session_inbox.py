"""Session inbox — mid-turn steer + post-turn queue (DSH-inspired).

Items live on the Redis/memory session document under ``inbox`` (list of dicts).
Claim operations remove matching items and return them for injection / enqueue.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from uuid import uuid4

InboxKind = Literal["steer", "queue"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_inbox_item(
    *,
    kind: InboxKind,
    content: str,
    source: str = "user",
) -> Dict[str, Any]:
    text = (content or "").strip()
    if not text:
        raise ValueError("inbox content must be non-empty")
    if kind not in ("steer", "queue"):
        raise ValueError("kind must be steer|queue")
    return {
        "id": f"inbox_{uuid4().hex[:16]}",
        "kind": kind,
        "content": text,
        "source": source or "user",
        "created_at": _now(),
    }


def list_inbox(session: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw = session.get("inbox") or []
    if not isinstance(raw, list):
        return []
    out: List[Dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict) and item.get("id") and item.get("content"):
            out.append(dict(item))
    return out


def push_inbox(session: Dict[str, Any], item: Dict[str, Any]) -> Dict[str, Any]:
    inbox = list_inbox(session)
    inbox.append(item)
    session["inbox"] = inbox
    session["updated_at"] = _now()
    return session


def remove_inbox(session: Dict[str, Any], item_id: str) -> Optional[Dict[str, Any]]:
    inbox = list_inbox(session)
    kept: List[Dict[str, Any]] = []
    removed: Optional[Dict[str, Any]] = None
    for item in inbox:
        if removed is None and str(item.get("id")) == str(item_id):
            removed = item
            continue
        kept.append(item)
    session["inbox"] = kept
    session["updated_at"] = _now()
    return removed


def clear_inbox(session: Dict[str, Any]) -> List[Dict[str, Any]]:
    prev = list_inbox(session)
    session["inbox"] = []
    session["updated_at"] = _now()
    return prev


def claim_kind(session: Dict[str, Any], kind: InboxKind) -> List[Dict[str, Any]]:
    """Remove and return all items of ``kind`` (FIFO within kind)."""
    inbox = list_inbox(session)
    claimed: List[Dict[str, Any]] = []
    kept: List[Dict[str, Any]] = []
    for item in inbox:
        if str(item.get("kind")) == kind:
            claimed.append(item)
        else:
            kept.append(item)
    session["inbox"] = kept
    session["updated_at"] = _now()
    return claimed


def claim_next_queue(session: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Remove and return the oldest queue item, if any."""
    inbox = list_inbox(session)
    if not inbox:
        return None
    for i, item in enumerate(inbox):
        if str(item.get("kind")) == "queue":
            claimed = item
            session["inbox"] = inbox[:i] + inbox[i + 1 :]
            session["updated_at"] = _now()
            return claimed
    return None
