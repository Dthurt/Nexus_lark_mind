"""Tests for ``.nlm/canvases/`` persistence."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.common.canvas_store import (
    CanvasWriteError,
    read_canvas_session_snapshot,
    write_canvas_session_snapshot,
    write_canvas_to_workspace,
)


def test_write_canvas_to_workspace(tmp_path: Path):
    out = write_canvas_to_workspace(
        str(tmp_path),
        file_name="Flow.mmd",
        content="# Flow\n\n```mermaid\ngraph TD; A-->B\n```\n",
    )
    assert out["ok"] is True
    assert out["path"] == ".nlm/canvases/Flow.mmd"
    dest = tmp_path / ".nlm" / "canvases" / "Flow.mmd"
    assert dest.is_file()
    assert "mermaid" in dest.read_text(encoding="utf-8")


def test_write_canvas_rejects_ssh_kind(tmp_path: Path):
    with pytest.raises(CanvasWriteError):
        write_canvas_to_workspace(str(tmp_path), file_name="x.md", content="hi", workspace_kind="ssh")


def test_write_canvas_softens_name(tmp_path: Path):
    out = write_canvas_to_workspace(str(tmp_path), file_name="../evil name!.md", content="x")
    assert out["path"] == ".nlm/canvases/evil_name_.md"


def test_canvas_session_snapshot_roundtrip(tmp_path: Path):
    state = {
        "open": False,
        "activeId": "cv_1",
        "docs": [{"id": "cv_1", "kind": "office", "title": "Paper", "body": "{}"}],
        "recent": [],
    }
    write_canvas_session_snapshot(str(tmp_path), session_id="sess_a", state=state)
    snap = read_canvas_session_snapshot(str(tmp_path), session_id="sess_a")
    assert snap is not None
    assert snap["open"] is False
    assert snap["docs"][0]["title"] == "Paper"
    assert read_canvas_session_snapshot(str(tmp_path), session_id="missing") is None
