"""Per-invoke workspace context for tools (session-bound)."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Any, Dict, Iterator, Optional

_workspace_cwd: ContextVar[Optional[str]] = ContextVar("nlm_workspace_cwd", default=None)
_workspace_meta: ContextVar[Optional[Dict[str, Any]]] = ContextVar("nlm_workspace_meta", default=None)


def get_workspace_cwd() -> Optional[str]:
    return _workspace_cwd.get()


def get_workspace_meta() -> Dict[str, Any]:
    return dict(_workspace_meta.get() or {})


def set_workspace_cwd(cwd: Optional[str]) -> Token:
    return _workspace_cwd.set((cwd or "").strip() or None)


def set_workspace_meta(meta: Optional[Dict[str, Any]]) -> Token:
    return _workspace_meta.set(dict(meta or {}) if meta else None)


def reset_workspace_cwd(token: Token) -> None:
    _workspace_cwd.reset(token)


def reset_workspace_meta(token: Token) -> None:
    _workspace_meta.reset(token)


@contextmanager
def workspace_cwd_scope(
    cwd: Optional[str],
    meta: Optional[Dict[str, Any]] = None,
) -> Iterator[Optional[str]]:
    token_cwd = set_workspace_cwd(cwd)
    token_meta = set_workspace_meta(meta)
    try:
        yield get_workspace_cwd()
    finally:
        reset_workspace_meta(token_meta)
        reset_workspace_cwd(token_cwd)
