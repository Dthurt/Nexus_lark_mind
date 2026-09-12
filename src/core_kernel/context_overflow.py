"""Detect provider errors that mean the prompt exceeded the context window."""

from __future__ import annotations

import re

_OVERFLOW_RE = re.compile(
    r"(?i)("
    r"context[\s_-]*(length|window)|"
    r"maximum[\s_-]*context|"
    r"prompt[\s_-]*(is\s+)?too[\s_-]*long|"
    r"token[\s_-]*(limit|count).*exceed|"
    r"exceed(ed|s)?[\s_-]*(the\s+)?(context|max).*token|"
    r"too many tokens|"
    r"max_tokens.*(?:prompt|input)|"
    r"input.*too\s*large|"
    r"reduce\s+the\s+length|"
    r"context_length_exceeded|"
    r"string_above_max_length"
    r")"
)


def is_context_overflow_error(exc: BaseException | str) -> bool:
    text = str(exc or "")
    if not text:
        return False
    return bool(_OVERFLOW_RE.search(text))
