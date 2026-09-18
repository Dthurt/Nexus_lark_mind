"""Layered context compaction — keep prompts under the model window.

Layers (DeepSeek-harness style):
  1. Soft-trim oversized single messages / tool payloads
  2. Collapse older middle turns into a framed structured checkpoint
  3. Hard-drop oldest non-system messages until under budget

Layer-2 uses a heuristic structured summary (no extra LLM call) framed like
DSH `<compacted-summary>` so the model treats it as established background.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.common.schemas import ChatMessage, ChatRole

DEFAULT_WINDOW = 128_000
# Reserve room for reply + tools schema
REPLY_RESERVE_RATIO = 0.18

# Profiles for COMPACTION_AGGRESSIVENESS / Settings.compaction_aggressiveness.
# conservative ≈ older thresholds (compress late); aggressive = current tight defaults.
COMPACTION_PROFILES: Dict[str, Dict[str, float]] = {
    "conservative": {
        "soft_msg_chars": 24_000,
        "target_ratio": 0.72,
        "collapse_trigger_ratio": 0.75,
    },
    "balanced": {
        "soft_msg_chars": 20_000,
        "target_ratio": 0.62,
        "collapse_trigger_ratio": 0.70,
    },
    "aggressive": {
        "soft_msg_chars": 16_000,
        "target_ratio": 0.55,
        "collapse_trigger_ratio": 0.62,
    },
}

# Module-level fallbacks (= balanced) for importers / tests that read constants.
SOFT_MSG_CHARS = int(COMPACTION_PROFILES["balanced"]["soft_msg_chars"])
TARGET_RATIO = float(COMPACTION_PROFILES["balanced"]["target_ratio"])
COLLAPSE_TRIGGER_RATIO = float(COMPACTION_PROFILES["balanced"]["collapse_trigger_ratio"])


def resolve_compaction_params(
    aggressiveness: Optional[str] = None,
) -> Dict[str, float]:
    """Return soft_msg_chars / target_ratio / collapse_trigger_ratio for a profile."""
    key = (aggressiveness or "").strip().lower()
    if not key:
        try:
            from src.common.config import get_settings

            key = str(get_settings().compaction_aggressiveness or "balanced").strip().lower()
        except Exception:
            key = "balanced"
    if key not in COMPACTION_PROFILES:
        key = "balanced"
    return dict(COMPACTION_PROFILES[key])

# Tags wrapping the structured summary inside the landed checkpoint node.
CHECKPOINT_PREAMBLE = (
    "This is an automatically generated checkpoint condensing an earlier span of "
    "the conversation to free up context. Treat the captured context as established "
    "background and build on it without restating it. Continue the task directly "
    "from the messages that follow, without acknowledging this checkpoint."
)

SUMMARY_OPEN = "<compacted-summary>"
SUMMARY_CLOSE = "</compacted-summary>"

# Keep aliases for importers that expect the old names
SUMMARY_OPEN_TAG = SUMMARY_OPEN
SUMMARY_CLOSE_TAG = SUMMARY_CLOSE

_SECTION_ORDER = (
    "Primary Request and Intent",
    "Key Technical Concepts",
    "Files and Code",
    "Errors and Fixes",
    "Pending Jobs",
    "Current Work",
    "Next Step",
    "Critical Context",
)

_MODEL_WINDOWS: List[Tuple[re.Pattern[str], int]] = [
    (re.compile(r"gpt-5", re.I), 400_000),
    (re.compile(r"gpt-4\.1", re.I), 1_048_576),
    (re.compile(r"gpt-4o-mini", re.I), 128_000),
    (re.compile(r"gpt-4o", re.I), 128_000),
    (re.compile(r"o3|o4-mini|o1", re.I), 200_000),
    (re.compile(r"claude", re.I), 200_000),
    (re.compile(r"deepseek", re.I), 64_000),
    (re.compile(r"glm-4|glm4", re.I), 128_000),
    (re.compile(r"qwen", re.I), 131_072),
]

_PATH_RE = re.compile(
    r"(?:^|[\s\"'`(])([A-Za-z0-9_./\\-]+\.(?:py|ts|tsx|js|jsx|vue|json|md|yml|yaml|toml|css|html|rs|go|java|kt|c|cpp|h|hpp|sql|sh|bat|ps1))\b"
)
_ERROR_RE = re.compile(
    r"(?i)(error|exception|traceback|failed|failure|cannot |denied|not found|TypeError|ValueError|AssertionError)"
)


def resolve_context_window(model_name: Optional[str] = None) -> int:
    name = str(model_name or "")
    for pat, window in _MODEL_WINDOWS:
        if pat.search(name):
            return window
    return DEFAULT_WINDOW


def estimate_tokens(text: str) -> int:
    s = text or ""
    if not s:
        return 0
    return max(1, (len(s) + 3) // 4)


def _msg_tokens(m: ChatMessage) -> int:
    n = estimate_tokens(m.content or "")
    if m.name:
        n += estimate_tokens(m.name)
    if m.tool_call_id:
        n += 8
    return n + 4  # role overhead


def _soft_trim_content(content: str, limit: int = SOFT_MSG_CHARS) -> str:
    if not content or len(content) <= limit:
        return content
    head = limit // 2
    tail = limit - head - 80
    return (
        content[:head]
        + f"\n\n…[truncated {len(content) - limit} chars]…\n\n"
        + content[-tail:]
    )


def _layer1_soft_trim(
    messages: Sequence[ChatMessage],
    *,
    soft_msg_chars: Optional[int] = None,
) -> List[ChatMessage]:
    limit = int(soft_msg_chars or resolve_compaction_params()["soft_msg_chars"])
    out: List[ChatMessage] = []
    for m in messages:
        content = m.content or ""
        if m.role == ChatRole.TOOL or len(content) > limit:
            content = _soft_trim_content(content, limit)
        if content == m.content:
            out.append(m)
        else:
            out.append(m.model_copy(update={"content": content}))
    return out


def _is_protected_tail(messages: Sequence[ChatMessage], idx: int) -> bool:
    """Keep the last user turn and anything after it intact."""
    last_user = -1
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].role == ChatRole.USER:
            last_user = i
            break
    if last_user < 0:
        return idx >= max(0, len(messages) - 4)
    return idx >= last_user


def _snippet(text: str, limit: int = 160) -> str:
    s = (text or "").strip().replace("\n", " ")
    if len(s) > limit:
        return s[: limit - 1] + "…"
    return s


def _parse_tool_blob(content: str) -> Dict[str, Any]:
    try:
        data = json.loads(content or "")
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _collect_paths(text: str, into: List[str], seen: set) -> None:
    for m in _PATH_RE.finditer(text or ""):
        p = m.group(1).replace("\\", "/")
        if p not in seen and len(p) < 200:
            seen.add(p)
            into.append(p)


def _build_structured_checkpoint(middle: Sequence[ChatMessage]) -> str:
    """Heuristic DSH-shaped checkpoint from dropped middle turns."""
    intents: List[str] = []
    files: List[str] = []
    file_seen: set = set()
    errors: List[str] = []
    concepts: List[str] = []
    pending: List[str] = []
    current: List[str] = []
    critical: List[str] = []
    tool_names: List[str] = []

    for m in middle:
        role = m.role
        text = m.content or ""
        _collect_paths(text, files, file_seen)

        if role == ChatRole.USER:
            sn = _snippet(text, 220)
            if sn and not sn.startswith("[context compacted"):
                intents.append(sn)
            if "prefer" in text.lower() or "不要" in text or "must" in text.lower():
                critical.append(sn)
        elif role == ChatRole.ASSISTANT:
            sn = _snippet(text, 180)
            meta = m.metadata or {}
            tcs = meta.get("tool_calls") or []
            if tcs:
                for tc in tcs[:8]:
                    fn = (tc.get("function") or {}) if isinstance(tc, dict) else {}
                    name = fn.get("name") or (tc.get("name") if isinstance(tc, dict) else "")
                    if name:
                        tool_names.append(str(name))
                        args_raw = fn.get("arguments") or ""
                        if isinstance(args_raw, str):
                            _collect_paths(args_raw, files, file_seen)
                            if "todo" in str(name).lower():
                                try:
                                    args = json.loads(args_raw or "{}")
                                    for it in (args.get("items") or args.get("todos") or [])[:6]:
                                        if isinstance(it, dict) and it.get("content"):
                                            st = str(it.get("status") or "")
                                            line = f"{st}: {it['content']}"
                                            if st == "completed":
                                                current.append(f"done — {it['content']}")
                                            else:
                                                pending.append(line)
                                except json.JSONDecodeError:
                                    pass
            if sn:
                current.append(sn)
            if _ERROR_RE.search(text):
                errors.append(sn)
        elif role == ChatRole.TOOL:
            blob = _parse_tool_blob(text)
            name = m.name or ""
            if name:
                tool_names.append(name)
            err = blob.get("error")
            if err:
                errors.append(_snippet(f"{name}: {err}", 180))
            result = blob.get("result")
            if isinstance(result, dict):
                path = result.get("path")
                if path:
                    _collect_paths(str(path), files, file_seen)
                if result.get("items") and "todo" in name.lower():
                    for it in result.get("items") or []:
                        if isinstance(it, dict) and it.get("content"):
                            pending.append(f"{it.get('status')}: {it['content']}")
            elif isinstance(result, str) and _ERROR_RE.search(result):
                errors.append(_snippet(f"{name}: {result}", 180))
            ok = blob.get("ok")
            if ok is False and not err:
                errors.append(_snippet(f"{name} failed", 120))

    if tool_names:
        uniq_tools = sorted({t.rsplit(".", 1)[-1] for t in tool_names})[:12]
        concepts.append("tools used: " + ", ".join(uniq_tools))

    def _uniq(rows: List[str], n: int) -> List[str]:
        out: List[str] = []
        seen: set = set()
        for r in rows:
            key = r[:80]
            if key in seen:
                continue
            seen.add(key)
            out.append(r)
            if len(out) >= n:
                break
        return out or ["(none)"]

    sections = {
        "Primary Request and Intent": _uniq(intents, 4),
        "Key Technical Concepts": _uniq(concepts, 6),
        "Files and Code": _uniq([f"- `{p}`" for p in files], 12),
        "Errors and Fixes": _uniq(errors, 6),
        "Pending Jobs": _uniq(pending, 8),
        "Current Work": _uniq(current[-4:], 4),
        "Next Step": _uniq(
            pending[:1] or (["continue from the recent messages below"] if current else ["(none)"]),
            1,
        ),
        "Critical Context": _uniq(critical, 6),
    }

    lines = [
        CHECKPOINT_PREAMBLE,
        "",
        SUMMARY_OPEN,
        f"(Dropped ~{len(middle)} older messages into this checkpoint.)",
        "",
    ]
    for title in _SECTION_ORDER:
        lines.append(f"## {title}")
        for bullet in sections[title]:
            if bullet.startswith("- "):
                lines.append(bullet)
            else:
                lines.append(f"- {bullet}")
        lines.append("")
    lines.append(SUMMARY_CLOSE)
    return "\n".join(lines).strip()


def _layer2_collapse_middle(messages: List[ChatMessage], budget: int) -> List[ChatMessage]:
    total = sum(_msg_tokens(m) for m in messages)
    if total <= budget or len(messages) <= 4:
        return list(messages)

    system = [m for m in messages if m.role == ChatRole.SYSTEM]
    rest = [m for m in messages if m.role != ChatRole.SYSTEM]
    if len(rest) <= 3:
        return list(messages)

    # Keep head (early user intent) + recent tail; collapse the middle.
    keep_head = min(2, max(1, len(rest) // 6))
    keep_tail = min(max(4, len(rest) // 3), len(rest) - keep_head)
    if keep_head + keep_tail >= len(rest):
        return list(messages)

    middle = rest[keep_head : len(rest) - keep_tail]
    if not middle:
        return list(messages)

    stub = ChatMessage(
        role=ChatRole.USER,
        content=_build_structured_checkpoint(middle),
        metadata={"compacted": True, "compacted_count": len(middle)},
    )
    return [*system, *rest[:keep_head], stub, *rest[len(rest) - keep_tail :]]


def _layer3_hard_drop(messages: List[ChatMessage], budget: int) -> List[ChatMessage]:
    msgs = list(messages)
    while len(msgs) > 2 and sum(_msg_tokens(m) for m in msgs) > budget:
        # Drop earliest non-system, non-protected message
        drop_at = None
        for i, m in enumerate(msgs):
            if m.role == ChatRole.SYSTEM:
                continue
            if _is_protected_tail(msgs, i):
                continue
            drop_at = i
            break
        if drop_at is None:
            # Still over: trim protected contents as last resort
            for i in range(len(msgs) - 1, -1, -1):
                if msgs[i].role == ChatRole.SYSTEM:
                    continue
                content = msgs[i].content or ""
                if len(content) > 800:
                    msgs[i] = msgs[i].model_copy(
                        update={"content": _soft_trim_content(content, 800)}
                    )
                    break
            else:
                break
            continue
        del msgs[drop_at]
    return msgs


def compact_messages(
    messages: Sequence[ChatMessage],
    *,
    model_name: Optional[str] = None,
    context_window: Optional[int] = None,
    aggressiveness: Optional[str] = None,
) -> List[ChatMessage]:
    """Return a copy of messages that fits under the model context budget."""
    params = resolve_compaction_params(aggressiveness)
    soft_chars = int(params["soft_msg_chars"])
    target_ratio = float(params["target_ratio"])
    collapse_ratio = float(params["collapse_trigger_ratio"])

    window = int(context_window or resolve_context_window(model_name))
    usable = max(4_000, int(window * (1.0 - REPLY_RESERVE_RATIO)))
    target = max(3_000, int(usable * target_ratio))
    collapse_at = max(3_000, int(usable * collapse_ratio))

    from src.core_kernel.tool_history import sanitize_tool_call_messages

    layer1 = _layer1_soft_trim(messages, soft_msg_chars=soft_chars)
    if sum(_msg_tokens(m) for m in layer1) <= collapse_at:
        return sanitize_tool_call_messages(layer1)

    layer2 = _layer2_collapse_middle(layer1, target)
    if sum(_msg_tokens(m) for m in layer2) <= usable:
        return sanitize_tool_call_messages(layer2)

    # Stronger collapse then hard drop toward target
    layer2b = _layer2_collapse_middle(layer2, int(target * 0.55))
    return sanitize_tool_call_messages(_layer3_hard_drop(layer2b, target))
