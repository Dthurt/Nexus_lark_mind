"""Persisted workspace (working directory) registry — DSH-inspired, NLM-local."""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

STORE_PATH = Path("data") / "workspaces.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonicalize_path(raw: str) -> Path:
    text = (raw or "").strip().strip('"')
    if not text:
        raise ValueError("path required")
    path = Path(text).expanduser()
    try:
        path = path.resolve(strict=False)
    except Exception:
        path = path.absolute()
    return path


def make_title(path: Path) -> str:
    return path.name or str(path)


class WorkspaceRecord(BaseModel):
    id: str
    path: str
    title: str = ""
    kind: str = "local"  # local | ssh
    ssh_host_id: str = ""
    session_ids: List[str] = Field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    def public(self) -> Dict[str, Any]:
        if self.kind == "ssh":
            return {
                "id": self.id,
                "path": self.path,
                "title": self.title or posix_basename(self.path),
                "kind": "ssh",
                "ssh_host_id": self.ssh_host_id,
                "exists": True,
                "is_dir": True,
                "session_ids": list(self.session_ids),
                "session_count": len(self.session_ids),
                "created_at": self.created_at,
                "updated_at": self.updated_at,
            }
        p = Path(self.path)
        return {
            "id": self.id,
            "path": self.path,
            "title": self.title or make_title(p),
            "kind": "local",
            "ssh_host_id": "",
            "exists": p.exists(),
            "is_dir": p.is_dir() if p.exists() else False,
            "session_ids": list(self.session_ids),
            "session_count": len(self.session_ids),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def posix_basename(path: str) -> str:
    text = (path or "").rstrip("/")
    if not text:
        return path or "/"
    return text.split("/")[-1] or text


class WorkspaceStore:
    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path or STORE_PATH
        self.workspaces: Dict[str, WorkspaceRecord] = {}
        self.load()

    def load(self) -> None:
        self.workspaces = {}
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            logger.exception("Failed reading %s", self.path)
            return
        for item in raw.get("workspaces") or []:
            try:
                rec = WorkspaceRecord.model_validate(item)
                self.workspaces[rec.id] = rec
            except Exception:
                logger.exception("Invalid workspace record")

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "workspaces": [w.model_dump() for w in sorted(self.workspaces.values(), key=lambda x: x.updated_at, reverse=True)]
        }
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def list_public(self) -> List[Dict[str, Any]]:
        items = [w.public() for w in self.workspaces.values()]
        items.sort(key=lambda x: x.get("updated_at") or "", reverse=True)
        return items

    def get(self, workspace_id: str) -> Optional[WorkspaceRecord]:
        return self.workspaces.get(workspace_id)

    def find_by_path(self, path: Path) -> Optional[WorkspaceRecord]:
        key = str(path)
        for w in self.workspaces.values():
            if w.kind == "local" and w.path == key:
                return w
        return None

    def find_ssh(self, ssh_host_id: str, remote_path: str) -> Optional[WorkspaceRecord]:
        for w in self.workspaces.values():
            if w.kind == "ssh" and w.ssh_host_id == ssh_host_id and w.path == remote_path:
                return w
        return None

    def create(self, raw_path: str, *, title: str = "") -> WorkspaceRecord:
        path = canonicalize_path(raw_path)
        if not path.exists():
            raise FileNotFoundError(f"path does not exist: {path}")
        if not path.is_dir():
            raise NotADirectoryError(f"not a directory: {path}")
        existing = self.find_by_path(path)
        if existing:
            existing.updated_at = _now()
            if title.strip():
                existing.title = title.strip()
            self.save()
            return existing
        now = _now()
        rec = WorkspaceRecord(
            id=f"ws_{uuid.uuid4().hex[:12]}",
            path=str(path),
            title=(title.strip() or make_title(path)),
            kind="local",
            created_at=now,
            updated_at=now,
        )
        self.workspaces[rec.id] = rec
        self.save()
        return rec

    def create_ssh(
        self,
        *,
        ssh_host_id: str,
        remote_path: str,
        title: str = "",
    ) -> WorkspaceRecord:
        remote_path = remote_path.rstrip("/") or remote_path
        existing = self.find_ssh(ssh_host_id, remote_path)
        if existing:
            existing.updated_at = _now()
            if title.strip():
                existing.title = title.strip()
            self.save()
            return existing
        now = _now()
        rec = WorkspaceRecord(
            id=f"ws_{uuid.uuid4().hex[:12]}",
            path=remote_path,
            title=(title.strip() or posix_basename(remote_path) or remote_path),
            kind="ssh",
            ssh_host_id=ssh_host_id,
            created_at=now,
            updated_at=now,
        )
        self.workspaces[rec.id] = rec
        self.save()
        return rec

    def delete(self, workspace_id: str) -> bool:
        if workspace_id not in self.workspaces:
            return False
        del self.workspaces[workspace_id]
        self.save()
        return True

    def attach_session(self, workspace_id: str, session_id: str) -> Optional[WorkspaceRecord]:
        rec = self.workspaces.get(workspace_id)
        if not rec:
            return None
        if session_id not in rec.session_ids:
            rec.session_ids.insert(0, session_id)
            rec.session_ids = rec.session_ids[:80]
        rec.updated_at = _now()
        self.save()
        return rec

    def detach_session(self, session_id: str) -> None:
        changed = False
        for rec in self.workspaces.values():
            if session_id in rec.session_ids:
                rec.session_ids = [s for s in rec.session_ids if s != session_id]
                rec.updated_at = _now()
                changed = True
        if changed:
            self.save()


_store: Optional[WorkspaceStore] = None


def get_workspace_store() -> WorkspaceStore:
    global _store
    if _store is None:
        _store = WorkspaceStore()
    return _store


def reload_workspace_store() -> WorkspaceStore:
    global _store
    _store = WorkspaceStore()
    return _store


def browse_directory(raw_path: str = "", *, limit: int = 120) -> Dict[str, Any]:
    """Lightweight local directory listing for workspace picker (local-first)."""
    if raw_path.strip():
        root = canonicalize_path(raw_path)
    else:
        root = Path.cwd().resolve()
    if not root.exists():
        raise FileNotFoundError(f"path does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"not a directory: {root}")
    entries: List[Dict[str, Any]] = []
    try:
        children = sorted(root.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except PermissionError as exc:
        raise PermissionError(f"cannot list: {root}") from exc
    for child in children[:limit]:
        name = child.name
        if name.startswith(".") and name not in {".env.example"}:
            # still show hidden? skip heavy noise like .git contents listing is ok to show .git itself
            pass
        entries.append(
            {
                "name": name,
                "path": str(child.resolve()) if child.exists() else str(child),
                "is_dir": child.is_dir(),
                "is_file": child.is_file(),
            }
        )
    parent = root.parent if root.parent != root else None
    return {
        "path": str(root),
        "parent": str(parent) if parent else None,
        "entries": entries,
        "title": make_title(root),
    }


_SAFE_REL = re.compile(r"^[^\x00]+$")


def resolve_under_workspace(cwd: str, rel_path: str = ".") -> Path:
    """Resolve a path against workspace cwd; reject escapes outside cwd.

    Absolute paths are allowed only when they still resolve under ``cwd``.
    ``..`` segments that climb above the workspace raise ``PermissionError``.
    """
    root = canonicalize_path(cwd)
    if not root.exists() or not root.is_dir():
        raise FileNotFoundError(f"workspace cwd missing: {root}")
    rel = (rel_path or ".").strip() or "."
    if not _SAFE_REL.match(rel):
        raise ValueError("invalid path")
    # Disallow Windows drive-hopping / UNC tricks that look relative but aren't.
    if rel.startswith("\\\\") or (len(rel) >= 2 and rel[1] == ":" and rel[0].isalpha()):
        candidate = Path(rel).resolve(strict=False)
    elif Path(rel).is_absolute():
        candidate = Path(rel).resolve(strict=False)
    else:
        candidate = (root / rel).resolve(strict=False)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise PermissionError(
            f"path escapes workspace sandbox (cwd={root}): {candidate}"
        ) from exc
    return candidate
