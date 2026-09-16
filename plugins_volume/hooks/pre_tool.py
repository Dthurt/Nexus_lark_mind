"""Example pre_tool hook — block writes to secrets.

Copy to a workspace as `.nlm/hooks/pre_tool.py`, or keep here under
`plugins_volume/hooks/pre_tool.py` for a global default.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


_BLOCKED_SUFFIXES = (
    ".env",
    ".env.local",
    ".env.production",
    "credentials.json",
    "secrets.json",
    "id_rsa",
    "id_ed25519",
)


def pre_tool(ctx: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    base = str(ctx.get("base") or "")
    if base not in {"write_file", "edit_file"}:
        return None
    args = dict(ctx.get("arguments") or {})
    path = str(args.get("path") or args.get("file") or "").replace("\\", "/")
    lower = path.lower()
    for suf in _BLOCKED_SUFFIXES:
        if lower.endswith(suf) or f"/{suf}" in lower:
            return {
                "block": True,
                "reason": f"pre_tool hook blocked mutating secret-like path: {path}",
            }
    return None
