"""LLM-backed context compaction (DeepSeek-harness summarizer shape).

Falls back to the heuristic structured checkpoint when no gateway is
available or the summarizer call fails.
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional, Sequence

from src.common.schemas import ChatMessage, ChatRole, ModelRequest
from src.core_kernel.context_compact import (
    CHECKPOINT_PREAMBLE,
    COLLAPSE_TRIGGER_RATIO,
    SUMMARY_CLOSE,
    SUMMARY_OPEN,
    TARGET_RATIO,
    REPLY_RESERVE_RATIO,
    _build_structured_checkpoint,
    _layer1_soft_trim,
    _layer3_hard_drop,
    _msg_tokens,
    compact_messages,
    resolve_context_window,
)

logger = logging.getLogger(__name__)

COMPACTION_INSTRUCTION = """You are now acting as a compaction engine for this AI coding assistant. Condense the conversation ABOVE into a structured checkpoint that lets another model resume the work with no loss of essential context.

Output EXACTLY the Markdown structure below: keep every section, in order. Use terse bullets, not prose paragraphs. Write "(none)" for an empty section — never drop a section.

## Primary Request and Intent
- [the user's original and evolving goals; quote verbatim where the exact wording matters]

## Key Technical Concepts
- [technologies, frameworks, patterns, and conventions in play]

## Files and Code
- [exact path: why it matters, key changes or snippets]

## Errors and Fixes
- [error: how it was resolved, plus any related user feedback]

## Pending Jobs
- [explicitly requested work not yet completed]

## Current Work
- [precisely what was in progress at this checkpoint]

## Next Step
- [the single next action, directly in line with the most recent request, or "(none)"]

## Critical Context
- [decisions and their rationale, constraints, user preferences, open questions, data needed to continue]

Rules:
- Write concise English or Chinese engineering prose matching the conversation language. Preserve exact file paths, commands, error strings, identifiers, numeric values, function signatures, and syntax fragments.
- Capture user feedback and explicit instructions faithfully, especially corrections.
- Do NOT mention this summarization request or that the context was compacted.
- Output only the checkpoint text: do not call any tool or take any other action.
- If the conversation already contains a <compacted-summary> block, it is a PRIOR checkpoint. Do not copy it forward verbatim: preserve still-true facts, drop stale ones, and merge newer information into a single consolidated summary under the same structure.
""".strip()

MAX_SUMMARY_CHARS = 12_000
MAX_MIDDLE_CHARS = 80_000


def frame_summary(body: str) -> str:
    text = (body or "").strip()
    if SUMMARY_OPEN in text and SUMMARY_CLOSE in text:
        # Model sometimes wraps itself — keep inner body
        try:
            inner = text.split(SUMMARY_OPEN, 1)[1].rsplit(SUMMARY_CLOSE, 1)[0].strip()
            if inner:
                text = inner
        except Exception:
            pass
    return f"{CHECKPOINT_PREAMBLE}\n\n{SUMMARY_OPEN}\n{text}\n{SUMMARY_CLOSE}"


def _serialize_for_summarizer(messages: Sequence[ChatMessage], *, limit: int) -> str:
    parts: List[str] = []
    size = 0
    for m in messages:
        role = m.role.value if hasattr(m.role, "value") else str(m.role)
        name = f" ({m.name})" if m.name else ""
        body = (m.content or "").strip()
        if len(body) > 4_000:
            body = body[:2_000] + "\n…[truncated]…\n" + body[-1_500:]
        chunk = f"[{role}{name}]\n{body}\n"
        if size + len(chunk) > limit:
            parts.append("…[earlier messages omitted for summarizer budget]…\n")
            break
        parts.append(chunk)
        size += len(chunk)
    return "\n".join(parts)


def _split_for_collapse(messages: List[ChatMessage]) -> Optional[tuple]:
    system = [m for m in messages if m.role == ChatRole.SYSTEM]
    rest = [m for m in messages if m.role != ChatRole.SYSTEM]
    if len(rest) <= 3:
        return None
    keep_head = min(2, max(1, len(rest) // 6))
    keep_tail = min(max(4, len(rest) // 3), len(rest) - keep_head)
    if keep_head + keep_tail >= len(rest):
        return None
    middle = rest[keep_head : len(rest) - keep_tail]
    if not middle:
        return None
    return system, rest, keep_head, keep_tail, middle


async def summarize_middle_with_llm(
    middle: Sequence[ChatMessage],
    *,
    gateway: Any,
    provider: Optional[str],
    model: Optional[str],
    task_id: Optional[str] = None,
) -> Optional[str]:
    """One-shot non-tool completion that produces a framed checkpoint body."""
    if gateway is None or not middle:
        return None
    transcript = _serialize_for_summarizer(middle, limit=MAX_MIDDLE_CHARS)
    if not transcript.strip():
        return None
    req = ModelRequest(
        provider=provider,
        model=model,
        messages=[
            ChatMessage(
                role=ChatRole.SYSTEM,
                content="You compress coding-agent conversations into structured checkpoints.",
            ),
            ChatMessage(role=ChatRole.USER, content=transcript),
            ChatMessage(role=ChatRole.USER, content=COMPACTION_INSTRUCTION),
        ],
        tools=None,
        stream=False,
        temperature=0.2,
        max_tokens=4096,
        metadata={"purpose": "compaction"},
    )
    try:
        resp = await gateway.complete(req, task_id=task_id)
        text = (resp.content or "").strip()
        if not text:
            return None
        if len(text) > MAX_SUMMARY_CHARS:
            text = text[: MAX_SUMMARY_CHARS - 40] + "\n…[truncated]…"
        return frame_summary(text)
    except Exception as exc:
        logger.warning("LLM compaction summarizer failed: %s", exc)
        return None


async def compact_messages_async(
    messages: Sequence[ChatMessage],
    *,
    model_name: Optional[str] = None,
    context_window: Optional[int] = None,
    gateway: Any = None,
    provider: Optional[str] = None,
    task_id: Optional[str] = None,
    use_llm: bool = True,
) -> tuple[List[ChatMessage], dict]:
    """Async compaction: soft-trim → optional LLM middle collapse → hard drop.

    Returns (messages, info) where info may include compacted_via / compacted_count.
    """
    info: dict = {}
    window = int(context_window or resolve_context_window(model_name))
    usable = max(4_000, int(window * (1.0 - REPLY_RESERVE_RATIO)))
    target = max(3_000, int(usable * TARGET_RATIO))
    collapse_at = max(3_000, int(usable * COLLAPSE_TRIGGER_RATIO))

    layer1 = _layer1_soft_trim(messages)
    total = sum(_msg_tokens(m) for m in layer1)
    # Compress once past soft trigger — don't wait until the hard usable ceiling.
    if total <= collapse_at:
        return layer1, info

    if use_llm and gateway is not None:
        split = _split_for_collapse(list(layer1))
        if split is not None:
            system, rest, keep_head, keep_tail, middle = split
            framed = await summarize_middle_with_llm(
                middle,
                gateway=gateway,
                provider=provider,
                model=model_name,
                task_id=task_id,
            )
            via = "llm"
            if not framed:
                framed = _build_structured_checkpoint(middle)
                via = "heuristic"
            stub = ChatMessage(
                role=ChatRole.USER,
                content=framed,
                metadata={
                    "compacted": True,
                    "compacted_count": len(middle),
                    "compacted_via": via,
                },
            )
            info = {"compacted_via": via, "compacted_count": len(middle)}
            layer2 = [*system, *rest[:keep_head], stub, *rest[len(rest) - keep_tail :]]
            if sum(_msg_tokens(m) for m in layer2) <= target:
                return layer2, info
            layer2b = compact_messages(layer2, model_name=model_name, context_window=int(window * 0.7))
            if sum(_msg_tokens(m) for m in layer2b) <= usable:
                return layer2b, info
            return _layer3_hard_drop(layer2b, target), info

    out = compact_messages(messages, model_name=model_name, context_window=context_window)
    if len(out) < len(messages):
        info = {"compacted_via": "heuristic"}
    return out, info
