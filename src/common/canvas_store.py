"""Write Canvas artifacts under ``{cwd}/.nlm/canvases/`` (local workspaces)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Optional


class CanvasWriteError(ValueError):
    pass


def _safe_file_name(name: str, *, default: str = "Canvas.md") -> str:
    raw = str(name or "").strip() or default
    base = Path(raw).name
    cleaned = re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", base)
    cleaned = cleaned.strip("._") or default
    if len(cleaned) > 120:
        stem = Path(cleaned).stem[:100]
        suf = Path(cleaned).suffix or Path(default).suffix or ".md"
        cleaned = stem + suf
    return cleaned


def write_canvas_to_workspace(
    cwd: str,
    *,
    file_name: str,
    content: str,
    workspace_kind: str = "local",
) -> Dict[str, Any]:
    """Persist a Canvas document under ``.nlm/canvases/``. Local only for now."""
    root = Path(str(cwd or "").strip()).expanduser().resolve()
    if not root.is_dir():
        raise CanvasWriteError(f"cwd is not a directory: {root}")
    kind = (workspace_kind or "local").strip().lower()
    if kind and kind != "local":
        raise CanvasWriteError("workspace canvas write supports local cwd only")

    name = _safe_file_name(file_name)
    dest_dir = root / ".nlm" / "canvases"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = (dest_dir / name).resolve()
    try:
        dest.relative_to(dest_dir.resolve())
    except ValueError as exc:
        raise CanvasWriteError("invalid canvas path") from exc

    text = str(content or "")
    dest.write_text(text, encoding="utf-8")
    rel = dest.relative_to(root).as_posix()
    return {
        "ok": True,
        "path": rel,
        "abs_path": str(dest),
        "bytes": len(text.encode("utf-8")),
    }


def _session_snapshot_name(session_id: str) -> str:
    safe = re.sub(r"[^\w.-]+", "_", str(session_id or "").strip()) or "session"
    return f"_session_{safe[:80]}.json"


def _canvas_dir(cwd: str, *, workspace_kind: str = "local") -> Path:
    root = Path(str(cwd or "").strip()).expanduser().resolve()
    if not root.is_dir():
        raise CanvasWriteError(f"cwd is not a directory: {root}")
    kind = (workspace_kind or "local").strip().lower()
    if kind and kind != "local":
        raise CanvasWriteError("workspace canvas write supports local cwd only")
    dest_dir = root / ".nlm" / "canvases"
    dest_dir.mkdir(parents=True, exist_ok=True)
    return dest_dir


def write_canvas_session_snapshot(
    cwd: str,
    *,
    session_id: str,
    state: Dict[str, Any],
    workspace_kind: str = "local",
) -> Dict[str, Any]:
    """Persist last Canvas tabs so closing the pane does not lose the document."""
    dest_dir = _canvas_dir(cwd, workspace_kind=workspace_kind)
    dest = (dest_dir / _session_snapshot_name(session_id)).resolve()
    try:
        dest.relative_to(dest_dir.resolve())
    except ValueError as exc:
        raise CanvasWriteError("invalid canvas path") from exc
    payload = {
        "session_id": session_id,
        "open": bool(state.get("open")),
        "activeId": state.get("activeId"),
        "docs": list(state.get("docs") or [])[:24],
        "recent": list(state.get("recent") or [])[:8],
    }
    dest.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return {"ok": True, "path": dest.as_posix(), "bytes": dest.stat().st_size}


def read_canvas_session_snapshot(
    cwd: str,
    *,
    session_id: str,
    workspace_kind: str = "local",
) -> Optional[Dict[str, Any]]:
    try:
        dest_dir = _canvas_dir(cwd, workspace_kind=workspace_kind)
    except CanvasWriteError:
        return None
    dest = dest_dir / _session_snapshot_name(session_id)
    if not dest.is_file():
        return None
    try:
        data = json.loads(dest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None
