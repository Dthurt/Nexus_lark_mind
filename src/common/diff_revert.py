"""Revert applied write_file / edit_file mutations (DiffDock reject)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from src.adapters.workspaces.store import resolve_under_workspace


class DiffRevertError(ValueError):
    pass


def revert_workspace_mutation(
    cwd: str,
    *,
    path: str,
    tool: str,
    workspace_kind: str = "local",
    created: bool = False,
    previous: str | None = None,
    old_string: str | None = None,
    new_string: str | None = None,
    replace_all: bool = False,
) -> Dict[str, Any]:
    kind = (workspace_kind or "local").strip().lower() or "local"
    if kind != "local":
        raise DiffRevertError("diff revert supports local cwd only")
    root = str(cwd or "").strip()
    if not root:
        raise DiffRevertError("cwd required")
    rel = str(path or "").strip().replace("\\", "/").lstrip("./")
    if not rel:
        raise DiffRevertError("path required")

    target = resolve_under_workspace(root, rel)
    base = (tool or "").strip().lower()

    if base == "write_file" or "write_file" in base:
        if created:
            if target.is_file():
                target.unlink()
            return {"ok": True, "path": rel, "action": "deleted"}
        if previous is None:
            raise DiffRevertError("previous content missing — cannot restore overwrite")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(str(previous), encoding="utf-8")
        return {"ok": True, "path": rel, "action": "restored", "bytes": len(str(previous).encode("utf-8"))}

    if base == "edit_file" or "edit_file" in base:
        if not target.is_file():
            raise DiffRevertError(f"file not found: {rel}")
        text = target.read_text(encoding="utf-8")
        old = str(old_string or "")
        new = str(new_string or "")
        if not new:
            raise DiffRevertError("new_string required to reverse edit")
        if new not in text:
            raise DiffRevertError("current file no longer contains new_string — manual fix needed")
        if replace_all:
            restored = text.replace(new, old)
        else:
            restored = text.replace(new, old, 1)
        target.write_text(restored, encoding="utf-8")
        return {"ok": True, "path": rel, "action": "reversed"}

    raise DiffRevertError(f"unsupported tool: {tool}")
