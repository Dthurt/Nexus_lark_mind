"""Nested streaming subagent runner (DSH-inspired, Nexus-native)."""

from __future__ import annotations

import asyncio
import time
from typing import Any, AsyncIterator, Dict, List, Optional

from src.common.schemas import ChatMessage, ChatRole
from src.core_kernel.model_gateway.gateway import ModelGateway
from src.core_kernel.plugin_runtime.manager import PluginManager
from src.core_kernel.subagent.registry import SubagentRecord, get_subagent_registry

MAX_SUBAGENT_DEPTH = 3

CHILD_SYSTEM = (
    "You are a Nexus Lark Mind subagent. Complete the delegated task thoroughly. "
    "Use workspace tools when a workspace is bound. Be concise in the final answer. "
    "When finished, summarize what you did and any remaining risks."
)


async def run_subagent_turn(
    *,
    gateway: ModelGateway,
    plugins: PluginManager,
    record: SubagentRecord,
    user_prompt: str,
    parent_call_id: str,
    task_id: Optional[str] = None,
    max_rounds: int = 16,
) -> AsyncIterator[Dict[str, Any]]:
    """Run one subagent turn; yield parent-SSE-friendly subagent chunks + final tool payload bits."""
    from src.common.config import get_settings
    from src.core_kernel.agent_runner import run_agent_stream

    settings = get_settings()
    child_rounds = max(int(max_rounds or 0), int(settings.subagent_max_rounds))

    registry = get_subagent_registry()
    rec = registry.get(record.id) or record
    rec.status = "running"
    if rec.cancel_event is None or rec.cancel_event.is_set():
        rec.cancel_event = asyncio.Event()

    messages: List[ChatMessage] = list(rec.messages)
    if not messages or messages[0].role != ChatRole.SYSTEM:
        messages = [ChatMessage(role=ChatRole.SYSTEM, content=CHILD_SYSTEM)] + [
            m for m in messages if m.role != ChatRole.SYSTEM
        ]
    messages.append(ChatMessage(role=ChatRole.USER, content=user_prompt))

    yield {
        "subagent": {
            "phase": "start",
            "subagent_id": rec.id,
            "parent_call_id": parent_call_id,
            "label": rec.label,
            "mode": rec.mode,
            "depth": rec.depth,
            "prompt": user_prompt,
        }
    }

    started = time.perf_counter()
    collected = ""
    error: Optional[str] = None

    # Temporarily restrict tools via filtering inside a custom loop by passing tools_enabled
    # and relying on agent_runner; we monkey-filter by wrapping plugins.as_openai_tools if needed.
    # Simplest: pass tools_enabled True and patch depth via workspace_meta flag consumed below.
    meta = dict(rec.workspace_meta or {})
    meta["subagent_depth"] = rec.depth
    meta["subagent_id"] = rec.id

    async for chunk in run_agent_stream(
        gateway=gateway,
        plugins=plugins,
        messages=messages,
        provider=rec.provider,
        model=rec.model,
        tools_enabled=True,
        task_id=task_id,
        max_rounds=child_rounds,
        workspace_cwd=rec.workspace_cwd,
        workspace_meta=meta,
        allow_subagents=rec.depth < MAX_SUBAGENT_DEPTH,
        cancel_event=rec.cancel_event,
        parent_session_id=rec.parent_session_id,
    ):
        if rec.cancel_event.is_set() and not chunk.get("done"):
            error = "interrupted"
            break
        if chunk.get("tool_call"):
            yield {
                "subagent": {
                    "phase": "tool_call",
                    "subagent_id": rec.id,
                    "parent_call_id": parent_call_id,
                    "tool_call": chunk["tool_call"],
                }
            }
            rec.transcript.append({"kind": "tool_call", **chunk["tool_call"]})
            continue
        if chunk.get("tool_result"):
            yield {
                "subagent": {
                    "phase": "tool_result",
                    "subagent_id": rec.id,
                    "parent_call_id": parent_call_id,
                    "tool_result": chunk["tool_result"],
                }
            }
            rec.transcript.append({"kind": "tool_result", **chunk["tool_result"]})
            continue
        if chunk.get("delta"):
            collected += chunk["delta"]
            yield {
                "subagent": {
                    "phase": "delta",
                    "subagent_id": rec.id,
                    "parent_call_id": parent_call_id,
                    "delta": chunk["delta"],
                }
            }
            continue
        if chunk.get("done"):
            if chunk.get("content"):
                collected = chunk["content"]
            if chunk.get("error"):
                error = chunk["error"]
            break

    duration_ms = (time.perf_counter() - started) * 1000
    if rec.cancel_event.is_set():
        rec.status = "interrupted"
        error = error or "interrupted"
    elif error:
        rec.status = "failed"
        rec.error = error
    else:
        rec.status = "idle"
        rec.error = ""

    rec.final_output = collected
    rec.messages = messages + [ChatMessage(role=ChatRole.ASSISTANT, content=collected or "")]
    rec.updated_at = time.time()

    try:
        await registry.persist(rec)
    except Exception:
        pass

    yield {
        "subagent": {
            "phase": "end",
            "subagent_id": rec.id,
            "parent_call_id": parent_call_id,
            "label": rec.label,
            "mode": rec.mode,
            "status": rec.status,
            "output": collected,
            "error": error,
            "duration_ms": duration_ms,
        }
    }
