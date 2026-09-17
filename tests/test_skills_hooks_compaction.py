"""Skills / hooks / compaction ledger unit tests."""

from __future__ import annotations

from pathlib import Path

from src.core_kernel.compaction_ledger import make_compaction_entry, notice_from_info
from src.core_kernel.skills_loader import (
    discover_skills,
    skill_playbook_block,
    skills_prompt_block,
)
from src.core_kernel.tool_hooks import run_pre_tool_hook


def test_discover_skills_from_nlm_dir(tmp_path: Path) -> None:
    skill = tmp_path / ".nlm" / "skills" / "demo" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        "---\nname: demo\ndescription: Demo skill\n---\n\n# Demo\nDo the thing.\n",
        encoding="utf-8",
    )
    skills = discover_skills(str(tmp_path))
    by_name = {s.name: s for s in skills}
    assert "demo" in by_name
    assert "Demo skill" in by_name["demo"].description
    block = skills_prompt_block(str(tmp_path))
    assert "demo" in block
    assert "progressive disclosure" in block.lower() or "Available skills" in block
    assert "injected" in block.lower()
    playbook = skill_playbook_block(str(tmp_path), "/skill:demo")
    assert "Do the thing." in playbook
    assert "Active skill: demo" in playbook


def test_pre_tool_hook_blocks_env(tmp_path: Path, monkeypatch) -> None:
    hooks = tmp_path / ".nlm" / "hooks"
    hooks.mkdir(parents=True)
    (hooks / "pre_tool.py").write_text(
        "def pre_tool(ctx):\n"
        "    p = str((ctx.get('arguments') or {}).get('path') or '')\n"
        "    if p.endswith('.env'):\n"
        "        return {'block': True, 'reason': 'no .env'}\n"
        "    return None\n",
        encoding="utf-8",
    )
    out = run_pre_tool_hook(
        tool="write_file",
        base="write_file",
        arguments={"path": "foo/.env", "content": "x"},
        cwd=str(tmp_path),
    )
    assert out.get("block") is True
    assert "env" in str(out.get("reason") or "").lower()

    ok = run_pre_tool_hook(
        tool="write_file",
        base="write_file",
        arguments={"path": "readme.md", "content": "x"},
        cwd=str(tmp_path),
    )
    assert ok.get("block") is False


def test_compaction_ledger_entry() -> None:
    entry = make_compaction_entry({"compacted_via": "llm", "compacted_count": 12})
    assert entry["kind"] == "compaction"
    assert entry["via"] == "llm"
    assert entry["compacted_count"] == 12
    assert "LLM" in notice_from_info({"compacted_via": "llm", "compacted_count": 3})
