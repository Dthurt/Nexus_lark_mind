"""Optional Python hook files (Pi-style extension points).

Search order (first existing file wins per hook name):
  <cwd>/.nlm/hooks/<name>.py
  plugins_volume/hooks/<name>.py

Supported modules:

  pre_tool.py        def pre_tool(ctx) -> {block?, arguments?, reason?}
  pre_compact.py     def pre_compact(ctx) -> {skip?, instructions?}
  post_compact.py    def post_compact(ctx) -> None
  session_persist.py def session_persist(ctx) -> {entries?}
"""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_HOOK_CACHE: dict[str, Any] = {}


def _hook_paths(name: str, cwd: Optional[str] = None) -> list[Path]:
    filename = f"{name}.py"
    paths: list[Path] = []
    if cwd:
        paths.append(Path(cwd) / ".nlm" / "hooks" / filename)
    paths.append(Path("plugins_volume") / "hooks" / filename)
    root = Path(__file__).resolve().parents[2]
    paths.append(root / "plugins_volume" / "hooks" / filename)
    return paths


def _load_hook(path: Path, attr: str) -> Any:
    key = f"{path.resolve()}::{attr}"
    mtime = path.stat().st_mtime
    cached = _HOOK_CACHE.get(key)
    if cached and cached.get("mtime") == mtime:
        return cached.get("fn")
    spec = importlib.util.spec_from_file_location(f"nlm_hook_{path.stem}_{attr}", path)
    if not spec or not spec.loader:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    fn = getattr(mod, attr, None)
    _HOOK_CACHE[key] = {"mtime": mtime, "fn": fn}
    return fn


def find_named_hook(name: str, attr: str, cwd: Optional[str] = None) -> Any:
    for path in _hook_paths(name, cwd):
        if path.is_file():
            try:
                return _load_hook(path, attr)
            except Exception as exc:
                logger.warning("%s hook load failed (%s): %s", name, path, exc)
    return None


def run_named_hook(
    name: str,
    attr: str,
    ctx: Dict[str, Any],
    cwd: Optional[str] = None,
) -> Dict[str, Any]:
    fn = find_named_hook(name, attr, cwd)
    if not callable(fn):
        return {}
    try:
        out = fn(ctx)
    except Exception as exc:
        logger.warning("%s hook error: %s", name, exc)
        return {}
    if not out:
        return {}
    if not isinstance(out, dict):
        return {}
    return out


def find_pre_tool_hook(cwd: Optional[str] = None) -> Any:
    return find_named_hook("pre_tool", "pre_tool", cwd)


def run_pre_tool_hook(
    *,
    tool: str,
    base: str,
    arguments: Dict[str, Any],
    plugin_id: Optional[str] = None,
    session_id: Optional[str] = None,
    task_id: Optional[str] = None,
    cwd: Optional[str] = None,
) -> Dict[str, Any]:
    """Returns {block, reason?, arguments?}."""
    ctx = {
        "tool": tool,
        "base": base,
        "arguments": dict(arguments or {}),
        "plugin_id": plugin_id,
        "session_id": session_id,
        "task_id": task_id,
        "cwd": cwd or "",
    }
    out = run_named_hook("pre_tool", "pre_tool", ctx, cwd)
    if not out:
        return {"block": False}
    result: Dict[str, Any] = {"block": bool(out.get("block"))}
    if out.get("reason"):
        result["reason"] = str(out["reason"])
    if isinstance(out.get("arguments"), dict):
        result["arguments"] = out["arguments"]
    return result


def run_pre_compact_hook(
    *,
    session_id: Optional[str] = None,
    cwd: Optional[str] = None,
    model: str = "",
    message_count: int = 0,
) -> Dict[str, Any]:
    """May return {skip: True} or {instructions: '...'} extra summarizer hints."""
    return run_named_hook(
        "pre_compact",
        "pre_compact",
        {
            "session_id": session_id or "",
            "cwd": cwd or "",
            "model": model,
            "message_count": message_count,
        },
        cwd,
    )


def run_post_compact_hook(
    *,
    session_id: Optional[str] = None,
    cwd: Optional[str] = None,
    compact_info: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return run_named_hook(
        "post_compact",
        "post_compact",
        {
            "session_id": session_id or "",
            "cwd": cwd or "",
            "compact_info": dict(compact_info or {}),
        },
        cwd,
    )


def run_session_persist_hook(
    *,
    session_id: str,
    cwd: Optional[str] = None,
    role: str = "",
    content: str = "",
) -> Dict[str, Any]:
    """May return {entries: [...]} stored on session.extension_entries."""
    return run_named_hook(
        "session_persist",
        "session_persist",
        {
            "session_id": session_id,
            "cwd": cwd or "",
            "role": role,
            "content": content,
        },
        cwd,
    )
