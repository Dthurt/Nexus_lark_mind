"""Shared tool-output truncation (Pi truncate.ts analogue)."""

from __future__ import annotations

from typing import Tuple

MAX_TOOL_LINES = 2000
MAX_TOOL_CHARS = 50_000


def truncate_tool_text(
    text: str,
    *,
    max_lines: int = MAX_TOOL_LINES,
    max_chars: int = MAX_TOOL_CHARS,
) -> Tuple[str, bool]:
    """Return (text, truncated). Dual line + byte/char cap."""
    s = text or ""
    truncated = False
    lines = s.splitlines()
    if len(lines) > max_lines:
        s = "\n".join(lines[:max_lines])
        truncated = True
    if len(s) > max_chars:
        s = s[:max_chars]
        truncated = True
    if truncated:
        s = s.rstrip() + "\n…[truncated]"
    return s, truncated
