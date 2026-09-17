"""Session tree helpers — fork lineage + bookmarks (Pi-inspired)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set


def build_session_tree(sessions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build a forest from sessions that carry parent_id / forked_from.

    Each node: session_id, title, parent_id, fork_point_index, children[], bookmarks?
    """
    by_id: Dict[str, Dict[str, Any]] = {}
    for s in sessions:
        if not isinstance(s, dict):
            continue
        sid = str(s.get("session_id") or "").strip()
        if not sid:
            continue
        parent = str(s.get("parent_id") or s.get("forked_from") or "").strip() or None
        by_id[sid] = {
            "session_id": sid,
            "title": s.get("title") or "新对话",
            "parent_id": parent,
            "fork_point_index": s.get("fork_point_index"),
            "updated_at": s.get("updated_at"),
            "created_at": s.get("created_at"),
            "message_count": s.get("message_count"),
            "bookmarks": list(s.get("bookmarks") or []),
            "workspace_id": s.get("workspace_id") or "",
            "children": [],
        }

    roots: List[Dict[str, Any]] = []
    for sid, node in by_id.items():
        parent = node.get("parent_id")
        if parent and parent in by_id and parent != sid:
            by_id[parent]["children"].append(node)
        else:
            if parent and parent not in by_id:
                node["orphan_parent_id"] = parent
            roots.append(node)

    def _sort(nodes: List[Dict[str, Any]]) -> None:
        nodes.sort(key=lambda n: str(n.get("updated_at") or ""), reverse=True)
        for n in nodes:
            _sort(n["children"])

    _sort(roots)
    return {
        "roots": roots,
        "node_count": len(by_id),
        "root_count": len(roots),
    }


def add_bookmark(
    bookmarks: Optional[List[Dict[str, Any]]],
    *,
    message_index: int,
    label: str = "",
) -> List[Dict[str, Any]]:
    out = [dict(b) for b in (bookmarks or []) if isinstance(b, dict)]
    # Replace existing bookmark at same index
    out = [b for b in out if int(b.get("message_index", -1)) != int(message_index)]
    out.append(
        {
            "message_index": int(message_index),
            "label": (label or f"Bookmark @{message_index}")[:80],
        }
    )
    out.sort(key=lambda b: int(b.get("message_index") or 0))
    return out


def remove_bookmark(
    bookmarks: Optional[List[Dict[str, Any]]],
    *,
    message_index: int,
) -> List[Dict[str, Any]]:
    return [
        dict(b)
        for b in (bookmarks or [])
        if isinstance(b, dict) and int(b.get("message_index", -1)) != int(message_index)
    ]


def lineage_ids(session: Dict[str, Any], lookup) -> List[str]:
    """Walk parent_id chain via async-incompatible sync lookup callable(sid)->dict|None."""
    chain: List[str] = []
    seen: Set[str] = set()
    cur: Optional[Dict[str, Any]] = session
    while cur:
        sid = str(cur.get("session_id") or "")
        if not sid or sid in seen:
            break
        seen.add(sid)
        chain.append(sid)
        parent = str(cur.get("parent_id") or cur.get("forked_from") or "").strip()
        if not parent:
            break
        cur = lookup(parent)
    return chain
