"""Skills / hooks / compaction ledger unit tests."""

from __future__ import annotations

from pathlib import Path

from src.core_kernel.compaction_ledger import make_compaction_entry, notice_from_info
from src.core_kernel.skills_loader import (
    discover_skills,
    skill_playbook_block,
    skills_prompt_block,
)
from src.core_kernel.tool_hooks import (
    run_post_compact_hook,
    run_pre_compact_hook,
    run_pre_tool_hook,
    run_session_persist_hook,
)


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


def test_discover_hidden_and_standalone_skill(tmp_path: Path) -> None:
    nlm = tmp_path / ".nlm" / "skills"
    nlm.mkdir(parents=True)
    (nlm / "hidden").mkdir()
    (nlm / "hidden" / "SKILL.md").write_text(
        "---\nname: hidden-skill\ndescription: Secret\ndisable-model-invocation: true\n---\n\n# Hidden\n",
        encoding="utf-8",
    )
    (nlm / "quick.md").write_text(
        "---\nname: quick-note\ndescription: Standalone playbook\n---\n\nDo it quickly.\n",
        encoding="utf-8",
    )
    skills = {s.name: s for s in discover_skills(str(tmp_path))}
    assert skills["hidden-skill"].hidden is True
    assert "quick-note" in skills
    block = skills_prompt_block(str(tmp_path))
    assert "hidden-skill" not in block
    assert "quick-note" in block
    play = skill_playbook_block(str(tmp_path), "/skill:hidden-skill")
    assert "Hidden" in play


def test_pre_compact_and_session_persist_hooks(tmp_path: Path) -> None:
    hooks = tmp_path / ".nlm" / "hooks"
    hooks.mkdir(parents=True)
    (hooks / "pre_compact.py").write_text(
        "def pre_compact(ctx):\n    return {'skip': True, 'instructions': 'keep paths'}\n",
        encoding="utf-8",
    )
    (hooks / "post_compact.py").write_text(
        "def post_compact(ctx):\n    return {'ok': True}\n",
        encoding="utf-8",
    )
    (hooks / "session_persist.py").write_text(
        "def session_persist(ctx):\n    return {'entries': [{'kind': 'ping'}]}\n",
        encoding="utf-8",
    )
    pre = run_pre_compact_hook(session_id="s1", cwd=str(tmp_path), model="x", message_count=3)
    assert pre.get("skip") is True
    post = run_post_compact_hook(session_id="s1", cwd=str(tmp_path), compact_info={"via": "llm"})
    assert post.get("ok") is True
    persist = run_session_persist_hook(session_id="s1", cwd=str(tmp_path), role="user")
    assert persist.get("entries") == [{"kind": "ping"}]


def test_extension_register_flag(monkeypatch, tmp_path: Path) -> None:
    from src.core_kernel.extension_runtime import ExtensionAPI, ExtensionRegistry

    reg = ExtensionRegistry()
    api = ExtensionAPI(name="demo", _bus=reg.bus, _registry=reg)
    api.register_flag(
        "strict",
        {"type": "boolean", "default": False, "env": "NLM_FLAG_STRICT"},
    )
    monkeypatch.delenv("NLM_FLAG_STRICT", raising=False)
    assert api.get_flag("strict") is False
    monkeypatch.setenv("NLM_FLAG_STRICT", "1")
    assert api.get_flag("strict") is True
    pub = reg.public_flags()
    assert pub[0]["name"] == "strict"
    assert pub[0]["value"] is True


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
