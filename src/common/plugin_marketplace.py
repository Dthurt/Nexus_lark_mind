"""Local plugin marketplace catalog (bundled volume + plugin_catalog packs)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from src.common.config import get_settings
from src.common.plugin_package import _plugins_root, load_manifest


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _catalog_root() -> Path:
    s = get_settings()
    root = Path(getattr(s, "plugin_catalog_dir", None) or "plugin_catalog")
    if not root.is_absolute():
        root = Path.cwd() / root
    return root


def _first_docstring(py_path: Path) -> str:
    try:
        text = py_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
    m = re.search(r'^"""(.*?)"""', text, re.S | re.M)
    if not m:
        m = re.search(r"^'''(.*?)'''", text, re.S | re.M)
    if not m:
        return ""
    body = m.group(1).strip()
    # First non-empty paragraph line
    for line in body.splitlines():
        line = line.strip()
        if line:
            return line[:200]
    return ""


def _scan_bundled() -> List[Dict[str, Any]]:
    root = _plugins_root()
    items: List[Dict[str, Any]] = []
    cli = root / "cli"
    if cli.is_dir():
        for path in sorted(cli.iterdir()):
            if not path.is_file() or path.suffix.lower() not in {".py", ".sh", ".js", ".ps1"}:
                continue
            if path.name.startswith("."):
                continue
            pid = f"cli.{path.stem}"
            items.append(
                {
                    "id": pid,
                    "name": path.stem.replace("_", " ").title(),
                    "kind": "cli",
                    "version": "bundled",
                    "description": _first_docstring(path) or f"Bundled CLI plugin ({path.name})",
                    "source": "bundled",
                    "path": str(path),
                    "installable": False,
                    "action": "enable",
                }
            )
    mcp = root / "mcp"
    if mcp.is_dir():
        for path in sorted(mcp.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            pid = str(data.get("plugin_id") or data.get("id") or path.stem).strip()
            if not pid:
                continue
            items.append(
                {
                    "id": pid,
                    "name": str(data.get("name") or pid),
                    "kind": str(data.get("kind") or "mcp"),
                    "version": str(data.get("version") or "bundled"),
                    "description": str(data.get("description") or "Bundled MCP plugin"),
                    "source": "bundled",
                    "path": str(path),
                    "installable": False,
                    "action": "enable",
                }
            )
    return items


def _scan_catalog_packs() -> List[Dict[str, Any]]:
    root = _catalog_root()
    items: List[Dict[str, Any]] = []
    if not root.is_dir():
        return items
    for child in sorted(root.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        manifest_path = child / "manifest.json"
        if not manifest_path.is_file():
            continue
        try:
            manifest = load_manifest(manifest_path)
        except Exception as exc:
            items.append(
                {
                    "id": child.name,
                    "name": child.name,
                    "kind": "unknown",
                    "version": "?",
                    "description": f"Invalid pack: {exc}",
                    "source": "catalog",
                    "path": str(child),
                    "installable": False,
                    "action": "fix",
                    "error": str(exc),
                }
            )
            continue
        pid = f"{manifest['kind']}.{manifest['id']}" if not str(manifest["id"]).startswith(
            ("cli.", "mcp.")
        ) else str(manifest["id"])
        # Prefer explicit plugin_id in manifest
        if manifest.get("plugin_id"):
            pid = str(manifest["plugin_id"])
        elif manifest["kind"] == "cli" and not str(manifest["id"]).startswith("cli."):
            pid = f"cli.{manifest['id']}"
        items.append(
            {
                "id": pid,
                "pack_id": manifest["id"],
                "name": str(manifest.get("label") or manifest.get("name") or manifest["id"]),
                "kind": manifest["kind"],
                "version": manifest.get("version") or "0.0.0",
                "description": str(manifest.get("description") or ""),
                "source": "catalog",
                "path": str(child),
                "installable": True,
                "action": "install",
                "has_sha256": bool(manifest.get("sha256")),
                "has_signature": bool(manifest.get("signature")),
            }
        )
    return items


def build_marketplace(*, installed_ids: Optional[Set[str]] = None) -> Dict[str, Any]:
    installed = {str(x) for x in (installed_ids or set())}
    bundled = _scan_bundled()
    packs = _scan_catalog_packs()
    # Deduplicate by id — catalog packs win over bundled listing for same id
    by_id: Dict[str, Dict[str, Any]] = {}
    for item in bundled + packs:
        pid = str(item.get("id") or "")
        if not pid:
            continue
        prev = by_id.get(pid)
        if prev and prev.get("source") == "catalog" and item.get("source") != "catalog":
            continue
        by_id[pid] = item

    items: List[Dict[str, Any]] = []
    for item in by_id.values():
        pid = str(item["id"])
        row = dict(item)
        row["installed"] = pid in installed
        items.append(row)
    items.sort(key=lambda x: (0 if x.get("source") == "catalog" else 1, str(x.get("name") or "").lower()))

    return {
        "items": items,
        "catalog_dir": str(_catalog_root()),
        "plugins_dir": str(_plugins_root()),
        "hints": [
            "本地市场：bundled = 已在 plugins_volume；catalog = plugin_catalog/ 可安装包",
            "也可粘贴本地目录路径或上传 zip（需含 manifest.json）",
            "公开远程目录仍未开放；签名校验见 PLUGIN_SIGNING_SECRET",
        ],
    }
