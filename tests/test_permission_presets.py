"""Tests for permission presets and sandbox path resolution."""

from pathlib import Path

import pytest

from src.adapters.workspaces.store import resolve_under_workspace
from src.common.permission_presets import (
    apply_preset_to_session_fields,
    blocks_mutating_tools,
    effective_auto_accept,
    normalize_plan_enforcement,
    normalize_preset,
    plan_hard_enforcement,
)


def test_normalize_preset_aliases():
    assert normalize_preset("read") == "read-only"
    assert normalize_preset("danger") == "danger-full-access"
    assert normalize_preset("nope") == "workspace-write"


def test_apply_preset_sets_auto_accept():
    assert apply_preset_to_session_fields("danger-full-access")["auto_accept"] is True
    assert apply_preset_to_session_fields("read-only")["auto_accept"] is False
    assert apply_preset_to_session_fields("workspace-write")["auto_accept"] is False


def test_effective_auto_accept_respects_explicit_flag():
    assert effective_auto_accept(permission_preset="read-only", auto_accept=True) is True
    assert effective_auto_accept(permission_preset="danger-full-access", auto_accept=False) is False
    assert effective_auto_accept(permission_preset="workspace-write", auto_accept=True) is True
    assert effective_auto_accept(permission_preset="danger-full-access", auto_accept=None) is True
    assert effective_auto_accept(permission_preset="read-only", auto_accept=None) is False


def test_plan_enforcement():
    assert plan_hard_enforcement("hard") is True
    assert plan_hard_enforcement("soft") is False
    assert normalize_plan_enforcement("SOFT") == "soft"
    assert blocks_mutating_tools("read-only") is True
    assert blocks_mutating_tools("workspace-write") is False


def test_sandbox_rejects_escape(tmp_path: Path):
    root = tmp_path / "ws"
    root.mkdir()
    inside = resolve_under_workspace(str(root), "a/b.txt")
    assert str(inside).startswith(str(root.resolve()))
    with pytest.raises(PermissionError):
        resolve_under_workspace(str(root), "../outside.txt")
