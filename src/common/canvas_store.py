"""Write Canvas artifacts under ``{cwd}/.nlm/canvases/`` (local workspaces)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict


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
