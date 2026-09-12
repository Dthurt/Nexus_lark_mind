"""Shared HITL approval timeouts (aligned with web/src/lib/approvalTimeout.ts)."""

from __future__ import annotations

from typing import Optional

APPROVAL_TIMEOUT_DEFAULT_S = 30.0
APPROVAL_TIMEOUT_SHELL_S = 60.0
APPROVAL_TIMEOUT_WRITE_S = 45.0
ASK_USER_TIMEOUT_S = 900.0
PLAN_REVIEW_TIMEOUT_S = 900.0


def approval_timeout_seconds(base_or_name: Optional[str] = None) -> float:
    """Graduated timeouts: shell / edits need more reading time."""
    b = str(base_or_name or "").strip().lower()
    leaf = b.split(".")[-1] if "." in b else b
    short = (
        leaf.replace("builtin_workspace_", "")
        .replace("builtin_", "")
        .replace("cli_", "")
    )
    if short in {"run_shell", "bash", "shell", "terminal", "exec", "run_code"}:
        return APPROVAL_TIMEOUT_SHELL_S
    if short in {"write_file", "edit_file", "apply_patch", "str_replace", "create_file"}:
        return APPROVAL_TIMEOUT_WRITE_S
    return APPROVAL_TIMEOUT_DEFAULT_S
