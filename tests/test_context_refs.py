"""Tests for @ context_refs expansion."""

from __future__ import annotations

from pathlib import Path

from src.common.context_refs import expand_context_refs, merge_user_content_with_context


def test_expand_file_and_merge(tmp_path: Path):
    f = tmp_path / "hello.py"
    f.write_text("print(1)\n", encoding="utf-8")
    block, meta = expand_context_refs(
        str(tmp_path),
        [{"path": "hello.py", "kind": "file"}],
    )
    assert "Attached context" in block
    assert "hello.py" in block
    assert "print(1)" in block
    assert meta[0]["ok"] is True
    merged = merge_user_content_with_context("fix this", block)
    assert merged.startswith("## Attached context")
    assert "## User request" in merged
    assert merged.endswith("fix this")


def test_expand_dir(tmp_path: Path):
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    block, meta = expand_context_refs(str(tmp_path), [{"path": ".", "kind": "dir"}])
    assert "directory" in block.lower() or "a.txt" in block
    assert meta[0]["kind"] == "dir"
