"""Local plugin package install (manifest + optional sha256 / HMAC signature)."""

from __future__ import annotations

import hashlib
import hmac
import json
import shutil
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.common.config import get_settings


class PluginPackageError(ValueError):
    pass


def _plugins_root() -> Path:
    s = get_settings()
    root = Path(getattr(s, "plugins_dir", None) or "plugins_volume")
    if not root.is_absolute():
        root = Path.cwd() / root
    return root


def load_manifest(path: Path) -> Dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise PluginPackageError("manifest.json must be an object")
    pid = str(data.get("id") or "").strip()
    if not pid:
        raise PluginPackageError("manifest.id required")
    kind = str(data.get("kind") or "cli").strip().lower()
    if kind not in {"cli", "mcp"}:
        raise PluginPackageError("manifest.kind must be cli or mcp")
    data["id"] = pid
    data["kind"] = kind
    data["version"] = str(data.get("version") or "0.0.0")
    return data


def verify_integrity(manifest: Dict[str, Any], package_dir: Path) -> List[str]:
    """Return warning strings; raise on hard failure when sha256/signature set."""
    warnings: List[str] = []
    expected = str(manifest.get("sha256") or "").strip().lower()
    files = sorted(
        p for p in package_dir.rglob("*") if p.is_file() and p.name != "manifest.json"
    )
    if expected:
        h = hashlib.sha256()
        for p in files:
            h.update(p.relative_to(package_dir).as_posix().encode())
            h.update(p.read_bytes())
        digest = h.hexdigest()
        if digest != expected:
            raise PluginPackageError(f"sha256 mismatch: got {digest[:12]}… expected {expected[:12]}…")
    else:
        warnings.append("unsigned package (no sha256)")

    sig = str(manifest.get("signature") or "").strip()
    secret = str(getattr(get_settings(), "plugin_signing_secret", "") or "").strip()
    if sig:
        if not secret:
            raise PluginPackageError("signature present but PLUGIN_SIGNING_SECRET unset")
        body = json.dumps(
            {k: manifest[k] for k in sorted(manifest) if k != "signature"},
            sort_keys=True,
            ensure_ascii=False,
        ).encode()
        expect = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expect, sig):
            raise PluginPackageError("HMAC signature invalid")
    elif secret:
        warnings.append("signing secret configured but package unsigned")
    return warnings


def install_from_directory(src: Path, *, reload: bool = True) -> Dict[str, Any]:
    src = src.resolve()
    if not src.is_dir():
        raise PluginPackageError("package path must be a directory")
    manifest_path = src / "manifest.json"
    if not manifest_path.is_file():
        raise PluginPackageError("manifest.json missing")
    manifest = load_manifest(manifest_path)
    warnings = verify_integrity(manifest, src)
    kind = manifest["kind"]
    dest_root = _plugins_root() / kind
    dest_root.mkdir(parents=True, exist_ok=True)
    dest = dest_root / manifest["id"]
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)

    # Flatten CLI: prefer entry.py at dest root for scanner
    entry = str(manifest.get("entry") or "").strip()
    if kind == "cli" and entry:
        entry_path = dest / entry
        if entry_path.is_file() and entry_path.name != f"{manifest['id']}.py":
            target = dest_root / f"{manifest['id']}.py"
            shutil.copy2(entry_path, target)
    if kind == "mcp":
        # Ensure a top-level JSON sibling for MCP glob scanners
        mcp_json = dest_root / f"{manifest['id']}.json"
        mcp_json.write_text(
            json.dumps(
                {
                    "id": manifest["id"],
                    "command": manifest.get("command"),
                    "args": manifest.get("args") or [],
                    "url": manifest.get("url"),
                    **{k: v for k, v in manifest.items() if k not in {"sha256", "signature"}},
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    return {
        "id": manifest["id"],
        "kind": kind,
        "version": manifest["version"],
        "path": str(dest),
        "warnings": warnings,
        "reload_hint": reload,
    }


def install_from_zip(zip_path: Path, *, extract_to: Optional[Path] = None) -> Dict[str, Any]:
    zip_path = zip_path.resolve()
    if not zip_path.is_file():
        raise PluginPackageError("zip not found")
    staging = extract_to or (Path("data") / "plugin_staging" / zip_path.stem)
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(staging)
    # If zip has a single root folder, use it
    children = [p for p in staging.iterdir()]
    root = children[0] if len(children) == 1 and children[0].is_dir() else staging
    if not (root / "manifest.json").is_file():
        # search one level
        found = next(staging.rglob("manifest.json"), None)
        if not found:
            raise PluginPackageError("manifest.json not found in zip")
        root = found.parent
    return install_from_directory(root)


def sign_manifest(manifest: Dict[str, Any], secret: str) -> str:
    body = json.dumps(
        {k: manifest[k] for k in sorted(manifest) if k != "signature"},
        sort_keys=True,
        ensure_ascii=False,
    ).encode()
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
