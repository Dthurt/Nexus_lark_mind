"""Local vs remote knowledge-base id helpers.

Session `weknora_kb_id` stores either a remote WeKnora id or a local library id
prefixed with ``local:``. Empty / ``local:default`` is the default SQLite library.
"""

from __future__ import annotations

from typing import List, Optional

LOCAL_KB_PREFIX = "local:"
DEFAULT_LOCAL_KB_ID = "local:default"
DEFAULT_LOCAL_KB_NAME = "默认知识库"
ALL_LOCAL_KB_ID = "local:all"
_ALL_LOCAL_KB_ALIASES = frozenset({"all", "local:all", "*", "local:*"})


def is_all_local_kbs(kb_id: str) -> bool:
    """True when search/reindex should union every local SQLite library."""
    return (kb_id or "").strip().lower() in _ALL_LOCAL_KB_ALIASES


def is_local_kb_id(kb_id: str) -> bool:
    s = (kb_id or "").strip()
    return (not s) or s.startswith(LOCAL_KB_PREFIX)


def is_remote_kb_id(kb_id: str) -> bool:
    s = (kb_id or "").strip()
    return bool(s) and not s.startswith(LOCAL_KB_PREFIX)


def normalize_local_kb_id(kb_id: str = "") -> str:
    s = (kb_id or "").strip()
    if not s or s in (LOCAL_KB_PREFIX.rstrip(":"), LOCAL_KB_PREFIX):
        return DEFAULT_LOCAL_KB_ID
    if s.startswith(LOCAL_KB_PREFIX):
        rest = s[len(LOCAL_KB_PREFIX) :].strip()
        return f"{LOCAL_KB_PREFIX}{rest}" if rest else DEFAULT_LOCAL_KB_ID
    return DEFAULT_LOCAL_KB_ID


def local_kb_match_values(kb_id: str = "") -> List[str]:
    """SQL IN-list for a bound local library (legacy empty kb_id counts as default)."""
    nid = normalize_local_kb_id(kb_id)
    if nid == DEFAULT_LOCAL_KB_ID:
        return ["", DEFAULT_LOCAL_KB_ID]
    return [nid]


def local_kb_label(kb_id: str = "", name: str = "") -> str:
    label = (name or "").strip()
    if label:
        return label
    nid = normalize_local_kb_id(kb_id)
    if nid == DEFAULT_LOCAL_KB_ID:
        return DEFAULT_LOCAL_KB_NAME
    return nid[len(LOCAL_KB_PREFIX) :] or DEFAULT_LOCAL_KB_NAME


def bound_is_remote(kb_id: str) -> bool:
    return is_remote_kb_id(kb_id)
