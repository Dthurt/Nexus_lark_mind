"""Feishu required provider/model picker helpers."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

REBIND_COMMANDS = frozenset(
    {
        "/model",
        "/models",
        "切换模型",
        "换模型",
        "选模型",
        "选择模型",
        "provider",
        "/provider",
    }
)

PRESET_COMMANDS = frozenset(
    {
        "/preset",
        "权限预设",
        "切换预设",
        "选择预设",
    }
)

KB_COMMANDS = frozenset(
    {
        "/kb",
        "切换知识库",
        "绑定知识库",
        "选择知识库",
    }
)


def is_rebind_command(text: str) -> bool:
    return (text or "").strip().lower() in {c.lower() for c in REBIND_COMMANDS}


def is_preset_command(text: str) -> bool:
    return (text or "").strip().lower() in {c.lower() for c in PRESET_COMMANDS}


def is_kb_command(text: str) -> bool:
    return (text or "").strip().lower() in {c.lower() for c in KB_COMMANDS}


def session_has_model(session: Optional[Dict[str, Any]]) -> bool:
    if not session:
        return False
    return bool(str(session.get("model_provider") or "").strip()) and bool(
        str(session.get("model_name") or "").strip()
    )


def catalog_choices(catalog: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Flatten configured providers into pickable entries."""
    providers = list((catalog or {}).get("providers") or [])
    out: List[Dict[str, Any]] = []
    for p in providers:
        if not isinstance(p, dict):
            continue
        pid = str(p.get("id") or "").strip()
        if not pid:
            continue
        if p.get("configured") is False:
            continue
        models = [str(m).strip() for m in (p.get("models") or []) if str(m).strip()]
        default_model = str(p.get("default_model") or "").strip()
        if default_model and default_model not in models:
            models.insert(0, default_model)
        if not models:
            continue
        out.append(
            {
                "id": pid,
                "label": str(p.get("label") or pid),
                "models": models,
                "default_model": default_model or models[0],
                "source": str(p.get("source") or ("custom" if not p.get("builtin") else "env")),
            }
        )
    return out


def page_slice(items: List[Any], page: int, page_size: int = 5) -> Tuple[List[Any], int, bool]:
    """Return (slice, page, has_more)."""
    page = max(0, int(page or 0))
    start = page * page_size
    chunk = items[start : start + page_size]
    has_more = start + page_size < len(items)
    return chunk, page, has_more
