import pytest

from src.common.errors import ValidationAppError
from src.core_kernel.plugin_runtime.invoke_context import workspace_cwd_scope
from src.core_kernel.plugin_runtime.lifecycle import PluginManifest
from src.core_kernel.plugin_runtime.office_store import get_outline, read_binary
from src.core_kernel.plugin_runtime.office_tools import TOOLS, OfficeToolsPlugin


@pytest.fixture
def office_env(tmp_path, monkeypatch):
    monkeypatch.setenv("NLM_OFFICE_DIR", str(tmp_path / "generated_office"))
    plugin = OfficeToolsPlugin(
        PluginManifest(plugin_id="builtin.office", name="Office", kind="inprocess")
    )
    return plugin, tmp_path


@pytest.mark.asyncio
async def test_office_tool_payloads_incremental(office_env):
    plugin, root = office_env
    cwd = root / "ws"
    cwd.mkdir()
    with workspace_cwd_scope(str(cwd), {"workspace_kind": "local"}):
        created = await plugin._on_invoke(
            "office_create",
            {
                "kind": "docx",
                "title": "季度方案",
                "throughline": "增长必须先对齐交付节奏",
                "plan": [{"id": "p1", "title": "背景"}, {"id": "p2", "title": "动作"}],
                "requirements": [{"id": "r1", "text": "写清背景", "mapped_to": "p1"}],
            },
        )
        assert created["ok"] is True
        assert created["doc_id"].startswith("off_")
        assert created["download_url"].startswith("/api/office/files/")
        assert "office_append" in created["hint"]
        assert (cwd / ".nlm" / "office").exists()

        with pytest.raises(ValidationAppError, match="PLAN only"):
            await plugin._on_invoke(
                "office_create",
                {
                    "kind": "docx",
                    "title": "X",
                    "throughline": "主线",
                    "plan": ["A"],
                    "blocks": [{"type": "paragraph", "text": "nope"}],
                },
            )

        appended = await plugin._on_invoke(
            "office_append",
            {
                "doc_id": created["doc_id"],
                "plan_id": "p1",
                "bridge": "承接封面主线，先把背景说清。",
                "blocks": [
                    {"type": "heading", "level": 2, "text": "背景", "req": "p1"},
                    {"type": "paragraph", "text": "本季重点是对齐交付。", "req": "p1"},
                    {"type": "equation", "latex": r"E = mc^2", "req": "p1"},
                ],
            },
        )
        assert appended["appended_ids"]
        outline = get_outline(created["doc_id"])
        assert outline is not None
        assert any(b.get("text") == "背景" for b in outline["blocks"])

        saved = await plugin._on_invoke("office_save", {"doc_id": created["doc_id"]})
        assert saved["ok"] is True
        path = read_binary(created["doc_id"], "docx")
        assert path is not None and path.is_file()
        assert path.stat().st_size > 1000


@pytest.mark.asyncio
async def test_office_ppt_create_append(office_env):
    plugin, root = office_env
    with workspace_cwd_scope(str(root), {"workspace_kind": "local"}):
        created = await plugin._on_invoke(
            "office_create",
            {"kind": "pptx", "title": "Kickoff", "throughline": "先讲目标", "plan": ["目标"]},
        )
        appended = await plugin._on_invoke(
            "office_append",
            {
                "doc_id": created["doc_id"],
                "slides": [
                    {
                        "type": "bullets",
                        "title": "目标",
                        "items": ["增长"],
                        "notes": "慢讲",
                        "req": "p1",
                    }
                ],
            },
        )
        assert appended["kind"] == "pptx"
        path = read_binary(created["doc_id"], "pptx")
        assert path is not None and path.suffix == ".pptx"


@pytest.mark.asyncio
async def test_office_revise_plan_and_missing_throughline(office_env):
    plugin, root = office_env
    with workspace_cwd_scope(str(root), {"workspace_kind": "local"}):
        with pytest.raises(ValidationAppError, match="throughline"):
            await plugin._on_invoke(
                "office_create",
                {"kind": "docx", "title": "X", "plan": ["A"]},
            )
        created = await plugin._on_invoke(
            "office_create",
            {"kind": "docx", "title": "Memo", "throughline": "主线", "plan": ["背景"]},
        )
        revised = await plugin._on_invoke(
            "office_revise_plan",
            {"doc_id": created["doc_id"], "add": [{"title": "动作", "after": "p1"}]},
        )
        assert revised["ok"] is True
        ids = [row["id"] for row in revised["outline"]["plan"]]
        assert "p1" in ids
        assert any(row["title"] == "动作" for row in revised["outline"]["plan"])


def test_tool_schemas_force_plan_and_types():
    names = {t["name"] for t in TOOLS}
    assert names == {
        "office_create",
        "office_append",
        "office_revise_plan",
        "office_replace",
        "office_save",
    }
    create = next(t for t in TOOLS if t["name"] == "office_create")
    assert "plan" in create["inputSchema"]["required"]
    assert "throughline" in create["inputSchema"]["required"]
    assert "PLAN" in create["description"] or "plan[]" in create["description"]
    append = next(t for t in TOOLS if t["name"] == "office_append")
    assert "one section" in append["description"] or "ONE" in append["description"]
    assert "plan_id" in append["inputSchema"]["properties"]
    block_enum = append["inputSchema"]["properties"]["blocks"]["items"]["properties"]["type"]["enum"]
    assert "quote" in block_enum and "table" in block_enum and "page_break" in block_enum
    assert "equation" in block_enum
    slide_enum = append["inputSchema"]["properties"]["slides"]["items"]["properties"]["type"]["enum"]
    assert "two_column" in slide_enum and "section" in slide_enum and "equation" in slide_enum
