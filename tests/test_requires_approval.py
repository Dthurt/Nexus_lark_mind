"""Unit tests for agent_runner._requires_approval."""

from src.core_kernel.agent_runner import (
    _requires_approval,
    _tool_leaf_name,
    office_plan_round_budget,
    office_save_succeeded,
)


def test_tool_leaf_strips_prefixes():
    assert _tool_leaf_name("builtin_workspace_write_file") == "write_file"
    assert _tool_leaf_name("cli_run_shell") == "run_shell"
    assert _tool_leaf_name("plugin.write_file") == "write_file"
    assert _tool_leaf_name("READ_FILE") == "read_file"


def test_safe_tools_skip_approval():
    for name in ("read_file", "grep", "glob", "list_dir", "web_search", "kb_search"):
        assert _requires_approval(name) is False
        assert _requires_approval(f"builtin_workspace_{name}") is False
    for name in ("office_create", "office_append", "office_revise_plan", "office_replace", "office_save"):
        assert _requires_approval(name) is False


def test_mutating_tools_need_approval():
    for name in ("write_file", "edit_file", "run_shell", "apply_patch", "str_replace", "create_file"):
        assert _requires_approval(name) is True
        assert _requires_approval(f"builtin_workspace_{name}") is True
        assert _requires_approval(f"workspace.{name}") is True


def test_shell_aliases_need_approval():
    for name in ("bash", "shell", "terminal", "exec"):
        assert _requires_approval(name) is True


def test_substring_false_positives_not_blocked():
    # Exact leaf match only — preview / dry-run helpers must not trip the gate.
    assert _requires_approval("preview_write_file_diff") is False
    assert _requires_approval("dry_run_shell_check") is False
    assert _requires_approval("write_file_preview") is False


def test_empty_name():
    assert _requires_approval("") is False
    assert _requires_approval("   ") is False


def test_office_save_succeeded_detects_ready_payload():
    assert office_save_succeeded({"success": True, "result": {"ok": True, "last_op": "save"}}) is True
    assert office_save_succeeded({"success": True, "result": {"outline": {"status": "ready"}}}) is True
    assert office_save_succeeded({"success": True, "result": {"ok": True, "last_op": "append"}}) is False
    assert office_save_succeeded({"success": False, "result": {"last_op": "save"}}) is False


def test_office_plan_round_budget_scales_with_plan():
    payload = {"result": {"outline": {"plan": [{"id": "p1"}] * 40}}}
    assert office_plan_round_budget(payload, base=8, cap=192) == 56
    assert office_plan_round_budget({"result": {}}, base=12, cap=192) == 16
