from pathlib import Path

from src.core_kernel.plugin_runtime.office_store import (
    list_recent_outlines,
    list_workspace_outlines,
    office_data_dir,
    persist_workspace_copy,
    put_outline,
)


def test_list_recent_outlines_reads_generated_files(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("NLM_OFFICE_DIR", str(tmp_path))
    office_data_dir()
    put_outline({"doc_id": "off_abc123", "kind": "docx", "title": "A"})
    items = list_recent_outlines(limit=4)
    assert items[0]["doc_id"] == "off_abc123"


def test_list_workspace_outlines(tmp_path: Path):
    src = tmp_path / "bin.docx"
    src.write_bytes(b"PK")
    persist_workspace_copy(
        str(tmp_path),
        file_name="paper.docx",
        src_binary=src,
        outline={"doc_id": "off_ws1", "kind": "docx", "title": "Paper"},
    )
    items = list_workspace_outlines(str(tmp_path), limit=4)
    assert items[0]["doc_id"] == "off_ws1"
