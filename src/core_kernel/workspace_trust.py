"""Workspace-folder trust for executing cwd Python extensions and hooks.

``plugins_volume`` stays trusted (bundled). ``<cwd>/.nlm/extensions`` and
``<cwd>/.nlm/hooks`` run only after the user marks that workspace trusted
(VS Code-style). Markdown skills remain readable either way.

Reads ``data/workspaces.json`` so the kernel does not import adapters.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

STORE_PATH = Path("data") / "workspaces.json"


def paths_equivalent(left: str, right: str) -> bool:
    """True when two local filesystem paths name the same folder.

    Windows / macOS compares are case-insensitive after normcase.
    """
    a = (left or "").strip()
    b = (right or "").strip()
    if not a or not b:
        return False
    if a == b:
        return True
    try:
        return os.path.normcase(os.path.normpath(a)) == os.path.normcase(os.path.normpath(b))
    except Exception:
        return False


def canonicalize_cwd(raw: str) -> Path:
    text = (raw or "").strip().strip('"')
    if not text:
        raise ValueError("cwd required")
    path = Path(text).expanduser()
    try:
        return path.resolve(strict=False)
    except Exception:
        return path.absolute()


def _load_records(store_path: Optional[Path] = None) -> list[Dict[str, Any]]:
    path = store_path or STORE_PATH
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.debug("workspace trust: failed reading %s", path, exc_info=True)
        return []
    rows = raw.get("workspaces") if isinstance(raw, dict) else None
    if not isinstance(rows, list):
        return []
    return [item for item in rows if isinstance(item, dict)]


def find_workspace_record(
    cwd: Optional[str] = None, *, store_path: Optional[Path] = None
) -> Optional[Dict[str, Any]]:
    if not (cwd or "").strip():
        return None
    records = _load_records(store_path)
    raw = (cwd or "").strip()
    local_key = ""
    try:
        local_key = str(canonicalize_cwd(raw))
    except Exception:
        local_key = raw
    ssh_key = raw.rstrip("/") or raw
    for item in records:
        kind = str(item.get("kind") or "local")
        stored = str(item.get("path") or "")
        if kind == "ssh":
            if stored.rstrip("/") == ssh_key or stored == raw:
                return item
            continue
        if paths_equivalent(stored, local_key) or paths_equivalent(stored, raw):
            return item
    return None


def is_workspace_code_allowed(
    cwd: Optional[str] = None, *, store_path: Optional[Path] = None
) -> bool:
    """True only when this cwd is a registered workspace with trusted=True."""
    rec = find_workspace_record(cwd, store_path=store_path)
    if not rec:
        return False
    return bool(rec.get("trusted"))
