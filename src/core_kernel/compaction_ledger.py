"""Compaction ledger — durable markers when context is checkpointed."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def make_compaction_entry(
    info: Dict[str, Any],
    *,
    round_index: Optional[int] = None,
) -> Dict[str, Any]:
    """Build a ledger entry from compact_messages_async info."""
    return {
        "kind": "compaction",
        "at": datetime.now(timezone.utc).isoformat(),
        "via": info.get("compacted_via") or "unknown",
        "compacted_count": int(info.get("compacted_count") or 0),
        "round": round_index,
        "summary_preview": str(info.get("summary_preview") or "")[:400],
    }


def append_compaction_ledger(session: dict, entry: Dict[str, Any]) -> None:
    """Mutate session dict in-place: session['compaction_ledger'] list."""
    ledger: List[Dict[str, Any]] = list(session.get("compaction_ledger") or [])
    ledger.append(entry)
    # Cap history
    session["compaction_ledger"] = ledger[-50:]


def notice_from_info(info: Dict[str, Any]) -> str:
    via = info.get("compacted_via") or ""
    n = int(info.get("compacted_count") or 0)
    if via == "llm":
        return f"上下文已压缩（LLM checkpoint，折叠 {n} 条）"
    if via == "heuristic":
        return f"上下文已压缩（启发式，折叠 {n} 条）"
    return "上下文已压缩"
