"""Permission presets — named bundles of sandbox + approval behavior.

Presets are session-scoped. Selecting one writes ``permission_preset`` and
derived ``auto_accept`` onto the Redis session document.
"""

from __future__ import annotations

from typing import Any, Dict, FrozenSet, Literal, Optional

PermissionPresetId = Literal["read-only", "workspace-write", "danger-full-access"]

# Tools that mutate the machine / workspace (used by read-only filter).
MUTATING_TOOLS: FrozenSet[str] = frozenset(
    {
        "write_file",
        "edit_file",
        "run_shell",
        "run_code",
        "apply_patch",
        "str_replace",
        "create_file",
        "bash",
        "shell",
        "terminal",
        "exec",
    }
)

PRESETS: Dict[str, Dict[str, Any]] = {
    "read-only": {
        "id": "read-only",
        "label": "只读",
        "hint": "禁止写文件与 shell",
        "auto_accept": False,
        "approval": "reject-mutating",  # mutating tools blocked / filtered
        "sandbox": "read-only",
    },
    "workspace-write": {
        "id": "workspace-write",
        "label": "工作区可写",
        "hint": "写/shell 需审批（Accept 可跳过）",
        "auto_accept": False,
        "approval": "ask",
        "sandbox": "workspace-write",
    },
    "danger-full-access": {
        "id": "danger-full-access",
        "label": "全权限",
        "hint": "写/shell 不再询问",
        "auto_accept": True,
        "approval": "never-ask",
        "sandbox": "danger",
    },
}

DEFAULT_PRESET: PermissionPresetId = "workspace-write"
PlanEnforcement = Literal["hard", "soft"]
DEFAULT_PLAN_ENFORCEMENT: PlanEnforcement = "hard"


def normalize_preset(value: Optional[str]) -> str:
    key = str(value or "").strip().lower().replace("_", "-")
    aliases = {
        "readonly": "read-only",
        "read": "read-only",
        "workspace": "workspace-write",
        "write": "workspace-write",
        "danger": "danger-full-access",
        "full": "danger-full-access",
        "full-access": "danger-full-access",
    }
    key = aliases.get(key, key)
    if key not in PRESETS:
        return DEFAULT_PRESET
    return key


def normalize_plan_enforcement(value: Optional[str]) -> str:
    v = str(value or "").strip().lower()
    if v in ("soft", "hard"):
        return v
    return DEFAULT_PLAN_ENFORCEMENT


def preset_config(preset_id: Optional[str]) -> Dict[str, Any]:
    pid = normalize_preset(preset_id)
    return dict(PRESETS[pid])


def apply_preset_to_session_fields(preset_id: Optional[str]) -> Dict[str, Any]:
    """Fields to merge into a session when selecting a preset."""
    cfg = preset_config(preset_id)
    return {
        "permission_preset": cfg["id"],
        "auto_accept": bool(cfg["auto_accept"]),
    }


def effective_auto_accept(
    *,
    permission_preset: Optional[str],
    auto_accept: Optional[bool],
) -> bool:
    """Session auto_accept wins when explicitly set; else preset default."""
    if auto_accept is not None:
        # danger preset forces accept; read-only never accepts mutating
        pid = normalize_preset(permission_preset)
        if pid == "read-only":
            return False
        if pid == "danger-full-access":
            return True
        return bool(auto_accept)
    return bool(preset_config(permission_preset)["auto_accept"])


def blocks_mutating_tools(permission_preset: Optional[str]) -> bool:
    return normalize_preset(permission_preset) == "read-only"


def plan_hard_enforcement(plan_enforcement: Optional[str]) -> bool:
    return normalize_plan_enforcement(plan_enforcement) == "hard"
