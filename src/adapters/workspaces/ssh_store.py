"""SSH remote hosts for coding-agent workspaces."""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

STORE_PATH = Path("data") / "ssh_hosts.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SshHostRecord(BaseModel):
    id: str
    label: str = ""
    host: str
    port: int = 22
    username: str
    auth_type: str = "password"  # password | key | agent
    source: str = "direct"  # direct | ssh_config
    ssh_config_alias: str = ""
    password: str = ""
    private_key: str = ""  # PEM text or path
    private_key_passphrase: str = ""
    default_path: str = "~"
    created_at: str = ""
    updated_at: str = ""

    def public(self) -> Dict[str, Any]:
        if self.source == "ssh_config" and self.ssh_config_alias:
            secret_set = True  # uses local ssh config / agent
            preview = "~/.ssh/config"
        else:
            secret_set = bool(self.password) if self.auth_type == "password" else bool(self.private_key)
            preview = ""
            if self.auth_type == "password" and self.password:
                preview = "****"
            elif self.private_key:
                preview = "key-set"
        display = self.ssh_config_alias if self.source == "ssh_config" and self.ssh_config_alias else (
            f"{self.username}@{self.host}:{self.port}"
        )
        return {
            "id": self.id,
            "label": self.label or display,
            "host": self.host,
            "port": self.port,
            "username": self.username,
            "auth_type": self.auth_type,
            "source": self.source,
            "ssh_config_alias": self.ssh_config_alias,
            "secret_set": secret_set,
            "secret_preview": preview,
            "default_path": self.default_path or "~",
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "display": display,
        }


class SshHostStore:
    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path or STORE_PATH
        self.hosts: Dict[str, SshHostRecord] = {}
        self.load()

    def load(self) -> None:
        self.hosts = {}
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            logger.exception("Failed reading %s", self.path)
            return
        for item in raw.get("hosts") or []:
            try:
                rec = SshHostRecord.model_validate(item)
                self.hosts[rec.id] = rec
            except Exception:
                logger.exception("Invalid ssh host record")

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "hosts": [
                h.model_dump()
                for h in sorted(self.hosts.values(), key=lambda x: x.updated_at, reverse=True)
            ]
        }
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def list_public(self) -> List[Dict[str, Any]]:
        items = [h.public() for h in self.hosts.values()]
        items.sort(key=lambda x: x.get("updated_at") or "", reverse=True)
        return items

    def get(self, host_id: str) -> Optional[SshHostRecord]:
        return self.hosts.get(host_id)

    def upsert(self, data: Dict[str, Any], *, keep_secret_if_blank: bool = True) -> SshHostRecord:
        host_id = str(data.get("id") or "").strip()
        existing = self.hosts.get(host_id) if host_id else None
        payload: Dict[str, Any] = existing.model_dump() if existing else {}
        for key, value in data.items():
            if key not in SshHostRecord.model_fields:
                continue
            if keep_secret_if_blank and key in {"password", "private_key", "private_key_passphrase"}:
                if value is None or (isinstance(value, str) and not value.strip()):
                    continue
            payload[key] = value
        if not payload.get("id"):
            payload["id"] = f"ssh_{uuid.uuid4().hex[:12]}"
        now = _now()
        payload.setdefault("created_at", now)
        payload["updated_at"] = now
        if not str(payload.get("host") or "").strip():
            if payload.get("source") == "ssh_config" and payload.get("ssh_config_alias"):
                payload["host"] = str(payload["ssh_config_alias"])
            else:
                raise ValueError("host required")
        if not str(payload.get("username") or "").strip():
            if payload.get("source") == "ssh_config":
                payload["username"] = payload.get("username") or "root"
            else:
                raise ValueError("username required")
        rec = SshHostRecord.model_validate(payload)
        if not rec.label:
            rec.label = rec.ssh_config_alias if rec.source == "ssh_config" else f"{rec.username}@{rec.host}"
        self.hosts[rec.id] = rec
        self.save()
        return rec

    def import_from_ssh_config(self, alias: str, *, label: str = "", default_path: str = "~") -> SshHostRecord:
        from src.adapters.workspaces.ssh_config import resolve_config_entry

        entry = resolve_config_entry(alias)
        if not entry:
            raise ValueError(f"ssh config alias not found: {alias}")
        # Reuse existing import by alias
        for h in self.hosts.values():
            if h.source == "ssh_config" and h.ssh_config_alias == alias:
                h.updated_at = _now()
                if label.strip():
                    h.label = label.strip()
                if default_path:
                    h.default_path = default_path
                self.save()
                return h
        now = _now()
        rec = SshHostRecord(
            id=f"ssh_{uuid.uuid4().hex[:12]}",
            label=label.strip() or alias,
            host=entry["hostname"],
            port=int(entry.get("port") or 22),
            username=entry.get("username") or os.environ.get("USER") or os.environ.get("USERNAME") or "root",
            auth_type="agent",
            source="ssh_config",
            ssh_config_alias=alias,
            private_key=entry.get("identity_file") or "",
            default_path=default_path or "~",
            created_at=now,
            updated_at=now,
        )
        self.hosts[rec.id] = rec
        self.save()
        return rec

    def delete(self, host_id: str) -> bool:
        if host_id not in self.hosts:
            return False
        del self.hosts[host_id]
        self.save()
        return True


_store: Optional[SshHostStore] = None
_store_mtime: float = 0.0


def _store_file_mtime() -> float:
    try:
        return STORE_PATH.stat().st_mtime
    except OSError:
        return 0.0


def get_ssh_host_store() -> SshHostStore:
    """Return the host store, reloading when ``data/ssh_hosts.json`` changes."""
    global _store, _store_mtime
    mtime = _store_file_mtime()
    if _store is None or mtime != _store_mtime:
        _store = SshHostStore()
        _store_mtime = mtime
    return _store


def reload_ssh_host_store() -> SshHostStore:
    global _store, _store_mtime
    _store = SshHostStore()
    _store_mtime = _store_file_mtime()
    return _store
