"""Parse local ~/.ssh/config for host aliases (OpenSSH format, lite)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional


def ssh_config_path() -> Path:
    custom = os.environ.get("SSH_CONFIG_FILE", "").strip()
    if custom:
        return Path(custom).expanduser()
    return Path.home() / ".ssh" / "config"


def _expand(path: str) -> str:
    return str(Path(path).expanduser())


def parse_ssh_config(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """
    Return Host entries from ssh config.
    Skips wildcard Host * and Include (MVP).
    """
    cfg = path or ssh_config_path()
    if not cfg.exists():
        return []
    try:
        lines = cfg.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []

    entries: List[Dict[str, Any]] = []
    current_aliases: List[str] = []
    current: Dict[str, Any] = {}

    def flush() -> None:
        nonlocal current_aliases, current
        if not current_aliases:
            return
        for alias in current_aliases:
            if alias == "*" or "?" in alias or "*" in alias:
                continue
            hostname = current.get("hostname") or alias
            user = current.get("user") or ""
            port = int(current.get("port") or 22)
            identity = current.get("identityfile") or ""
            entries.append(
                {
                    "alias": alias,
                    "hostname": hostname,
                    "username": user,
                    "port": port,
                    "identity_file": _expand(identity) if identity else "",
                    "display": f"{user}@{hostname}:{port}" if user else f"{hostname}:{port}",
                    "config_path": str(cfg),
                }
            )
        current_aliases = []
        current = {}

    for raw in lines:
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split(None, 1)
        key = parts[0].lower()
        val = parts[1].strip() if len(parts) > 1 else ""
        if key == "host":
            flush()
            current_aliases = val.split()
        elif key in {"hostname", "user", "port", "identityfile"}:
            if key == "port":
                try:
                    current[key] = int(val)
                except ValueError:
                    current[key] = 22
            else:
                current[key] = val
        elif key == "include":
            # MVP: skip nested includes
            pass
    flush()

    # de-dupe by alias
    seen = set()
    out: List[Dict[str, Any]] = []
    for e in entries:
        if e["alias"] in seen:
            continue
        seen.add(e["alias"])
        out.append(e)
    out.sort(key=lambda x: x["alias"].lower())
    return out


def resolve_config_entry(alias: str, path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    for e in parse_ssh_config(path):
        if e["alias"] == alias:
            return e
    return None
