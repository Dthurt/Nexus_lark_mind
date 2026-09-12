"""Write Delivery artifacts under ``{cwd}/.nlm/deliveries/`` (local workspaces)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Optional


class DeliveryWriteError(ValueError):
    pass


_SAFE_NAME = re.compile(r"^[A-Za-z0-9._\u4e00-\u9fff-]{1,120}$")


def _safe_file_name(name: str) -> str:
    raw = str(name or "").strip() or "Delivery.md"
    base = Path(raw).name
    if not base.endswith(".md"):
        base = f"{base}.md"
    # soften unsafe chars
    cleaned = re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", base)
    cleaned = cleaned.strip("._") or "Delivery.md"
    if not cleaned.endswith(".md"):
        cleaned += ".md"
    if len(cleaned) > 120:
        cleaned = cleaned[:116] + ".md"
    return cleaned


def write_delivery_to_workspace(
    cwd: str,
    *,
    file_name: str,
    content: str,
    workspace_kind: str = "local",
) -> Dict[str, Any]:
    """Persist Delivery markdown under ``.nlm/deliveries/``. Local only for now."""
    root = Path(str(cwd or "").strip()).expanduser().resolve()
    if not root.is_dir():
        raise DeliveryWriteError(f"cwd is not a directory: {root}")
    kind = (workspace_kind or "local").strip().lower()
    if kind and kind != "local":
        raise DeliveryWriteError("workspace delivery write supports local cwd only")

    name = _safe_file_name(file_name)
    dest_dir = root / ".nlm" / "deliveries"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = (dest_dir / name).resolve()
    # Escape check
    try:
        dest.relative_to(dest_dir.resolve())
    except ValueError as exc:
        raise DeliveryWriteError("invalid delivery path") from exc

    text = str(content or "")
    dest.write_text(text, encoding="utf-8")
    rel = dest.relative_to(root).as_posix()
    return {
        "ok": True,
        "path": rel,
        "abs_path": str(dest),
        "bytes": len(text.encode("utf-8")),
    }
