"""Optional pre-tool hooks (Pi-style extension points).

Search order (first existing file wins):
  <cwd>/.nlm/hooks/pre_tool.py
  plugins_volume/hooks/pre_tool.py

Hook module must define:

  def pre_tool(ctx: dict) -> dict | None:
      '''Return {"block": True, "reason": "..."} to deny, or None/{} to allow.
      Optional: {"arguments": {...}} to rewrite tool args.
      '''

``ctx`` keys: tool, base, arguments, plugin_id, session_id, task_id, cwd
"""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_HOOK_CACHE: dict[str, Any] = {}


def _hook_paths(cwd: Optional[str] = None) -> list[Path]:
    paths: list[Path] = []
    if cwd:
        paths.append(Path(cwd) / ".nlm" / "hooks" / "pre_tool.py")
    # Repo-relative plugins_volume (process cwd is usually repo root)
    paths.append(Path("plugins_volume") / "hooks" / "pre_tool.py")
    root = Path(__file__).resolve().parents[2]
    paths.append(root / "plugins_volume" / "hooks" / "pre_tool.py")
    return paths


def _load_hook(path: Path) -> Any:
    key = str(path.resolve())
    mtime = path.stat().st_mtime
    cached = _HOOK_CACHE.get(key)
    if cached and cached.get("mtime") == mtime:
        return cached.get("fn")
    spec = importlib.util.spec_from_file_location(f"nlm_pre_tool_{path.stem}", path)
    if not spec or not spec.loader:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    fn = getattr(mod, "pre_tool", None)
    _HOOK_CACHE[key] = {"mtime": mtime, "fn": fn}
    return fn


def find_pre_tool_hook(cwd: Optional[str] = None) -> Any:
    for path in _hook_paths(cwd):
        if path.is_file():
            try:
                return _load_hook(path)
            except Exception as exc:
                logger.warning("pre_tool hook load failed (%s): %s", path, exc)
    return None


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
    fn = find_pre_tool_hook(cwd)
    if not callable(fn):
        return {"block": False}
    ctx = {
        "tool": tool,
        "base": base,
        "arguments": dict(arguments or {}),
        "plugin_id": plugin_id,
        "session_id": session_id,
        "task_id": task_id,
        "cwd": cwd or "",
    }
    try:
        out = fn(ctx)
    except Exception as exc:
        logger.warning("pre_tool hook error: %s", exc)
        return {"block": False}
    if not out:
        return {"block": False}
    if not isinstance(out, dict):
        return {"block": False}
    result: Dict[str, Any] = {"block": bool(out.get("block"))}
    if out.get("reason"):
        result["reason"] = str(out["reason"])
    if isinstance(out.get("arguments"), dict):
        result["arguments"] = out["arguments"]
    return result
