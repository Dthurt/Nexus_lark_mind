"""Persist Office outlines + binaries (workspace + downloadable cache)."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.core_kernel.plugin_runtime.office_outline import OfficeOutlineError

_REPO_ROOT = Path(__file__).resolve().parents[3]
_LOCK = threading.Lock()
_MEM: Dict[str, Dict[str, Any]] = {}


def office_data_dir() -> Path:
    override = (os.environ.get("NLM_OFFICE_DIR") or "").strip()
    root = Path(override) if override else (_REPO_ROOT / "data" / "generated_office")
    root.mkdir(parents=True, exist_ok=True)
    (root / "assets").mkdir(parents=True, exist_ok=True)
    return root


def _safe_name(name: str, *, default: str = "document") -> str:
    raw = str(name or "").strip() or default
    base = Path(raw).name
    cleaned = re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", base).strip("._") or default
    if len(cleaned) > 120:
        cleaned = Path(cleaned).stem[:100] + (Path(cleaned).suffix or "")
    return cleaned


def outline_path(doc_id: str) -> Path:
    return office_data_dir() / f"{_safe_name(doc_id, default='off')}.json"


def binary_path(doc_id: str, kind: str) -> Path:
    ext = ".pptx" if kind == "pptx" else ".docx"
    return office_data_dir() / f"{_safe_name(doc_id, default='off')}{ext}"


def put_outline(outline: Dict[str, Any]) -> Dict[str, Any]:
    doc_id = str(outline.get("doc_id") or "").strip()
    if not doc_id:
        raise OfficeOutlineError("outline missing doc_id")
    with _LOCK:
        _MEM[doc_id] = outline
        dest = outline_path(doc_id)
        dest.write_text(json.dumps(outline, ensure_ascii=False, indent=2), encoding="utf-8")
    return outline


def get_outline(doc_id: str) -> Optional[Dict[str, Any]]:
    key = str(doc_id or "").strip()
    if not key:
        return None
    with _LOCK:
        hit = _MEM.get(key)
        if hit:
            return hit
    path = outline_path(key)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(data, dict):
        with _LOCK:
            _MEM[key] = data
        return data
    return None


def write_binary(doc_id: str, kind: str, data: bytes) -> Path:
    dest = binary_path(doc_id, kind)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return dest


def read_binary(doc_id: str, kind: str = "") -> Optional[Path]:
    if kind:
        path = binary_path(doc_id, kind)
        return path if path.is_file() else None
    for k in ("docx", "pptx"):
        path = binary_path(doc_id, k)
        if path.is_file():
            return path
    return None


def download_url(doc_id: str) -> str:
    return f"/api/office/files/{doc_id}"


def copy_asset(src: Path, *, doc_id: str) -> Tuple[Path, str]:
    """Copy an image into the downloadable asset cache. Returns (path, url)."""
    raw = src.read_bytes()
    digest = hashlib.sha1(raw).hexdigest()[:12]
    ext = src.suffix.lower() if src.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp"} else ".png"
    name = f"{_safe_name(doc_id)}_{digest}{ext}"
    dest = office_data_dir() / "assets" / name
    if not dest.exists():
        dest.write_bytes(raw)
    return dest, f"/api/office/assets/{name}"


def resolve_asset_file(name: str) -> Optional[Path]:
    safe = Path(str(name or "")).name
    if not safe or ".." in safe:
        return None
    path = office_data_dir() / "assets" / safe
    return path if path.is_file() else None


def persist_workspace_copy(
    cwd: str,
    *,
    file_name: str,
    src_binary: Path,
    outline: Dict[str, Any],
    workspace_kind: str = "local",
) -> Dict[str, Any]:
    """Write `{cwd}/.nlm/office/` copies. Local workspaces only."""
    root = Path(str(cwd or "").strip()).expanduser()
    try:
        root = root.resolve()
    except Exception:
        root = root.absolute()
    if not root.is_dir():
        return {"ok": False, "error": f"cwd is not a directory: {root}"}
    kind = (workspace_kind or "local").strip().lower()
    if kind and kind != "local":
        return {"ok": False, "error": "office workspace write supports local cwd only"}
    dest_dir = root / ".nlm" / "office"
    dest_dir.mkdir(parents=True, exist_ok=True)
    name = _safe_name(file_name, default=src_binary.name)
    dest = (dest_dir / name).resolve()
    try:
        dest.relative_to(dest_dir.resolve())
    except ValueError:
        return {"ok": False, "error": "invalid office path"}
    shutil.copy2(src_binary, dest)
    meta = dest_dir / f"{Path(name).stem}.outline.json"
    meta.write_text(json.dumps(outline, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        rel = dest.relative_to(root).as_posix()
    except ValueError:
        rel = dest.as_posix()
    return {"ok": True, "path": rel, "abs_path": str(dest), "bytes": dest.stat().st_size}


def list_recent_outlines(*, limit: int = 8) -> List[Dict[str, Any]]:
    """Newest generated_office outlines (by mtime). Does not change the contract."""
    root = office_data_dir()
    files = [p for p in root.glob("off_*.json") if p.is_file()]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    out: List[Dict[str, Any]] = []
    for path in files[: max(1, int(limit or 8))]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict) and data.get("doc_id"):
            out.append(data)
    return out


def list_workspace_outlines(cwd: str, *, limit: int = 8) -> List[Dict[str, Any]]:
    """Newest ``{cwd}/.nlm/office/*.outline.json`` copies."""
    root = Path(str(cwd or "").strip()).expanduser()
    try:
        root = root.resolve()
    except Exception:
        root = root.absolute()
    dest = root / ".nlm" / "office"
    if not dest.is_dir():
        return []
    files = [p for p in dest.glob("*.outline.json") if p.is_file()]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    out: List[Dict[str, Any]] = []
    for path in files[: max(1, int(limit or 8))]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict) and data.get("doc_id"):
            out.append(data)
    return out


def suggested_file_name(outline: Dict[str, Any]) -> str:
    kind = outline.get("kind") or "docx"
    ext = ".pptx" if kind == "pptx" else ".docx"
    explicit = str(outline.get("file_name") or "").strip()
    if explicit:
        name = _safe_name(explicit)
        if not name.lower().endswith(ext):
            name = Path(name).stem + ext
        return name
    title = _safe_name(str(outline.get("title") or "document"), default="document")
    return f"{title}{ext}"
