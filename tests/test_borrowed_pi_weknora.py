"""Local adaptations from Pi / WeKnora / WeMM leftovers."""

from __future__ import annotations

import io
import zipfile

import pytest

from src.core_kernel.file_ops import extract_file_ops, format_file_operations, heuristic_branch_summary
from src.core_kernel.plugin_runtime.knowledge_ingest import OFFICE_SUFFIXES, read_file_as_text
from src.core_kernel.plugin_runtime.knowledge_rerank import local_rerank_scores, rerank_hits
from src.core_kernel.tool_output import truncate_tool_text
from src.core_kernel.workspace_git import format_git_prompt_block


def test_local_rerank_prefers_overlap():
    scores = local_rerank_scores("vector search", ["unrelated cooking", "vector search hybrid"])
    assert scores[1] > scores[0]


@pytest.mark.asyncio
async def test_rerank_hits_reorders():
    hits = [
        {"title": "cook", "snippet": "recipe", "score": 9},
        {"title": "kb", "snippet": "hybrid vector search", "score": 1},
    ]
    out = await rerank_hits("vector search", hits, keep=2)
    assert out[0]["title"] == "kb"
    assert "rerank" in out[0]


def test_file_ops_from_tool_calls():
    msgs = [
        {
            "role": "assistant",
            "tool_calls": [
                {"function": {"name": "read_file", "arguments": '{"path": "src/a.py"}'}},
                {"function": {"name": "edit_file", "arguments": '{"path": "src/a.py"}'}},
            ],
        }
    ]
    reads, writes = extract_file_ops(msgs)
    assert "src/a.py" in reads
    assert "src/a.py" in writes
    blob = format_file_operations(msgs)
    assert "read-files" in blob
    assert "modified-files" in blob


def test_branch_summary_mentions_user():
    text = heuristic_branch_summary(
        [{"role": "user", "content": "try plan B on the auth module"}]
    )
    assert "auth" in text.lower()


def test_truncate_tool_text_dual_cap():
    long = "\n".join(f"line{i}" for i in range(3000))
    out, cut = truncate_tool_text(long, max_lines=10, max_chars=500)
    assert cut
    assert "[truncated]" in out
    assert out.count("\n") <= 12


def test_office_docx_extract(tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "word/document.xml",
            '<?xml version="1.0"?><w:document><w:t>HelloNexusDocx</w:t></w:document>',
        )
    path = tmp_path / "note.docx"
    path.write_bytes(buf.getvalue())
    assert path.suffix in OFFICE_SUFFIXES
    text, note = read_file_as_text(path)
    assert "HelloNexusDocx" in text
    assert "OOXML" in note


def test_git_prompt_block_dirty():
    block = format_git_prompt_block(
        {
            "is_repo": True,
            "branch": "feat/x",
            "dirty": True,
            "changed_files": 2,
            "insertions": 4,
            "deletions": 1,
        }
    )
    assert "feat/x" in block
    assert "dirty" in block
