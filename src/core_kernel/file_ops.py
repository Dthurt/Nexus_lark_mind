"""Extract read/modified file paths from tool history (Pi compaction utils)."""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Sequence, Set, Tuple

_READ = {"read_file", "kb_read", "weknora_read", "list_dir", "glob", "grep"}
_WRITE = {"write_file", "edit_file", "apply_patch", "kb_add", "kb_sync_docs"}


def _name(msg: Any) -> str:
    if isinstance(msg, dict):
        return str(msg.get("name") or "")
    return str(getattr(msg, "name", "") or "")


def _content(msg: Any) -> str:
    if isinstance(msg, dict):
        return str(msg.get("content") or "")
    return str(getattr(msg, "content", "") or "")


def _tool_calls(msg: Any) -> List[Dict[str, Any]]:
    raw = msg.get("tool_calls") if isinstance(msg, dict) else getattr(msg, "tool_calls", None)
    return [c for c in (raw or []) if isinstance(c, dict)]


def _paths_from_args(raw: Any) -> List[str]:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            return []
    if not isinstance(raw, dict):
        return []
    out: List[str] = []
    for key in ("path", "file", "file_path", "target"):
        v = raw.get(key)
        if isinstance(v, str) and v.strip():
            out.append(v.strip())
    return out


def extract_file_ops(messages: Sequence[Any]) -> Tuple[List[str], List[str]]:
    """Return (read_paths, modified_paths) in first-seen order."""
    reads: List[str] = []
    writes: List[str] = []
    seen_r: Set[str] = set()
    seen_w: Set[str] = set()

    def _add(bucket: List[str], seen: Set[str], path: str) -> None:
        if path and path not in seen:
            seen.add(path)
            bucket.append(path)

    for msg in messages:
        name = _name(msg)
        for call in _tool_calls(msg):
            fn = str(call.get("function") or {})
            if isinstance(call.get("function"), dict):
                fn_name = str(call["function"].get("name") or "")
                args = call["function"].get("arguments")
            else:
                fn_name = str(call.get("name") or "")
                args = call.get("arguments")
            for p in _paths_from_args(args):
                if fn_name in _WRITE:
                    _add(writes, seen_w, p)
                else:
                    _add(reads, seen_r, p)
        if name in _READ:
            body = _content(msg)
            try:
                data = json.loads(body) if body.startswith("{") else {}
            except Exception:
                data = {}
            if isinstance(data, dict):
                for p in _paths_from_args(data):
                    _add(reads, seen_r, p)
                if data.get("path"):
                    _add(reads, seen_r, str(data["path"]))
        if name in _WRITE:
            body = _content(msg)
            try:
                data = json.loads(body) if body.startswith("{") else {}
            except Exception:
                data = {}
            if isinstance(data, dict) and data.get("path"):
                _add(writes, seen_w, str(data["path"]))
    return reads, writes


def format_file_operations(messages: Sequence[Any], *, limit: int = 24) -> str:
    reads, writes = extract_file_ops(messages)
    if not reads and not writes:
        return ""
    lines = ["## File operations (from tools)"]
    if reads:
        lines.append("read-files:")
        for p in reads[:limit]:
            lines.append(f"- {p}")
    if writes:
        lines.append("modified-files:")
        for p in writes[:limit]:
            lines.append(f"- {p}")
    return "\n".join(lines)


def heuristic_branch_summary(messages: Iterable[Any], *, max_chars: int = 1200) -> str:
    """Cheap abandoned-branch recap without an extra LLM call."""
    items = list(messages)
    reads, writes = extract_file_ops(items)
    users = []
    for m in items:
        role = m.get("role") if isinstance(m, dict) else getattr(m, "role", "")
        role_s = role.value if hasattr(role, "value") else str(role or "")
        if role_s != "user":
            continue
        text = _content(m).strip().replace("\n", " ")
        if text and "<knowledge_context" not in text:
            users.append(text[:160])
    lines = []
    if users:
        lines.append("User asks: " + " | ".join(users[-3:]))
    if writes:
        lines.append("Modified: " + ", ".join(writes[:8]))
    if reads:
        lines.append("Read: " + ", ".join(reads[:8]))
    text = "\n".join(lines) or "(empty branch)"
    return text[:max_chars]
