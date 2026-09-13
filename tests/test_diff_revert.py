"""Tests for DiffDock revert helper."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.common.diff_revert import DiffRevertError, revert_workspace_mutation


def test_revert_edit(tmp_path: Path):
    f = tmp_path / "x.txt"
    f.write_text("hi world", encoding="utf-8")
    out = revert_workspace_mutation(
        str(tmp_path),
        path="x.txt",
        tool="edit_file",
        old_string="hello",
        new_string="hi",
    )
    assert out["action"] == "reversed"
    assert f.read_text(encoding="utf-8") == "hello world"


def test_revert_write_created(tmp_path: Path):
    f = tmp_path / "new.txt"
    f.write_text("fresh", encoding="utf-8")
    out = revert_workspace_mutation(
        str(tmp_path),
        path="new.txt",
        tool="write_file",
        created=True,
    )
    assert out["action"] == "deleted"
    assert not f.exists()


def test_revert_write_restore(tmp_path: Path):
    f = tmp_path / "old.txt"
    f.write_text("NEW", encoding="utf-8")
    out = revert_workspace_mutation(
        str(tmp_path),
        path="old.txt",
        tool="write_file",
        created=False,
        previous="OLD",
    )
    assert out["action"] == "restored"
    assert f.read_text(encoding="utf-8") == "OLD"


def test_revert_ssh_rejected(tmp_path: Path):
    with pytest.raises(DiffRevertError):
        revert_workspace_mutation(str(tmp_path), path="a", tool="write_file", workspace_kind="ssh")
