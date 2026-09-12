"""Experience tier + reasoning effort (Wave D session controls)."""

from __future__ import annotations

import re
from typing import Any, Dict, Optional, Sequence

EXPERIENCE_TIERS = ("fast", "balanced", "high")
REASONING_EFFORTS = ("low", "medium", "high")

_TIER_META: Dict[str, Dict[str, str]] = {
    "fast": {
        "label": "Fast",
        "diagrams": "Mermaid only — do NOT emit ```drawio / mxfile XML fences.",
    },
    "balanced": {
        "label": "Balanced",
        "diagrams": "Prefer Mermaid; use Draw.io XML only when layout/precision matters.",
    },
    "high": {
        "label": "High",
        "diagrams": "Prefer Draw.io XML for architecture / multi-lane boards; Mermaid OK for simple flows.",
    },
}

# Soft floors (0=weak, 1=mid, 2=strong) — UX hint only; never hard-block the request.
_TIER_MODEL_FLOOR: Dict[str, int] = {"fast": 0, "balanced": 1, "high": 2}
_WEAK_MODEL_RE = re.compile(
    r"(flash|mini|nano|haiku|lite|tiny|3\.5-turbo|gpt-3\.5|4o-mini|4\.1-nano|"
    r"qwen.*0\.5|1\.5b|1b|3b)",
    re.I,
)
_STRONG_MODEL_RE = re.compile(
    r"(opus|sonnet|gpt-4(?!o-mini)|o1|o3|o4|r1|reasoner|plus|pro(?!-mini)|"
    r"claude-3-5|claude-4|deepseek-v3|qwen.*72|70b|405b)",
    re.I,
)


def normalize_experience_tier(value: Optional[str]) -> str:
    key = str(value or "").strip().lower()
    if key in ("1", "fast", "low"):
        return "fast"
    if key in ("3", "high", "max"):
        return "high"
    if key in ("2", "balanced", "medium", "default", ""):
        return "balanced"
    if key in EXPERIENCE_TIERS:
        return key
    return "balanced"


def normalize_reasoning_effort(value: Optional[str]) -> str:
    key = str(value or "").strip().lower()
    if key in ("min", "minimal", "none"):
        return "low"
    if key in ("max", "xhigh", "extra"):
        return "high"
    if key in REASONING_EFFORTS:
        return key
    if not key:
        return "medium"
    return "medium"


def experience_tier_prompt_block(tier: Optional[str]) -> str:
    tid = normalize_experience_tier(tier)
    meta = _TIER_META[tid]
    return (
        f"## Experience tier: {meta['label']} (`{tid}`)\n"
        f"- Diagrams: {meta['diagrams']}\n"
        "- Stay within this tier unless the user explicitly asks for another fidelity.\n"
    )


def reasoning_effort_hint(effort: Optional[str]) -> str:
    eid = normalize_reasoning_effort(effort)
    return (
        f"## Reasoning effort: `{eid}`\n"
        "- Match depth of analysis to this session setting "
        "(low = brief; medium = default; high = deeper trade-offs).\n"
    )


def apply_experience_fields(
    experience_tier: Optional[str] = None,
    reasoning_effort: Optional[str] = None,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if experience_tier is not None:
        out["experience_tier"] = normalize_experience_tier(experience_tier)
    if reasoning_effort is not None:
        out["reasoning_effort"] = normalize_reasoning_effort(reasoning_effort)
    return out


def model_strength(model_name: Optional[str]) -> int:
    """Heuristic 0=weak / 1=mid / 2=strong for soft tier floors."""
    name = str(model_name or "").strip()
    if not name:
        return 0
    if _WEAK_MODEL_RE.search(name):
        return 0
    if _STRONG_MODEL_RE.search(name):
        return 2
    return 1


def tier_meets_model_floor(
    experience_tier: Optional[str],
    model_name: Optional[str],
) -> bool:
    tid = normalize_experience_tier(experience_tier)
    floor = _TIER_MODEL_FLOOR.get(tid, 1)
    return model_strength(model_name) >= floor


def suggest_stronger_model(
    candidates: Sequence[str],
    current: Optional[str] = None,
) -> Optional[str]:
    """Return the strongest candidate strictly above current strength, if any."""
    cur = str(current or "").strip()
    best: Optional[str] = None
    best_s = model_strength(cur)
    for raw in candidates:
        name = str(raw or "").strip()
        if not name or name == cur:
            continue
        s = model_strength(name)
        if s > best_s:
            best = name
            best_s = s
    return best


def tier_model_floor_hint(
    experience_tier: Optional[str],
    model_name: Optional[str],
    candidates: Optional[Sequence[str]] = None,
) -> Optional[Dict[str, Any]]:
    """Soft UX payload when the selected model is below the tier floor."""
    tid = normalize_experience_tier(experience_tier)
    if tier_meets_model_floor(tid, model_name):
        return None
    suggestion = suggest_stronger_model(list(candidates or []), model_name)
    return {
        "tier": tid,
        "model": str(model_name or "").strip(),
        "suggestion": suggestion,
        "message": (
            f"体验档 `{tid}` 建议使用更强模型"
            + (f"（可考虑 `{suggestion}`）" if suggestion else "（当前模型偏弱）")
        ),
    }
