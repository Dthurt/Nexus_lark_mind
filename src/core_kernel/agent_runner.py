"""Streaming agent turn with optional tool-calling rounds and nested subagents."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, AsyncIterator, Dict, List, Optional

from src.common.schemas import ChatMessage, ChatRole, ModelRequest, PluginInvokeRequest
from src.core_kernel.model_gateway.gateway import ModelGateway
from src.core_kernel.plugin_runtime.invoke_context import workspace_cwd_scope
from src.core_kernel.plugin_runtime.manager import PluginManager
from src.core_kernel import user_gate

SUBAGENT_STREAM_TOOLS = {"subagent", "subagent_fork", "send_message"}
SUBAGENT_CONTROL_TOOLS = {"interrupt_agent", "list_agents"}
SUBAGENT_ALL = SUBAGENT_STREAM_TOOLS | SUBAGENT_CONTROL_TOOLS
ASK_USER_TOOL = "ask_user"
TODO_WRITE_TOOL = "todo_write"
OPEN_CANVAS_TOOL = "open_canvas"
EXIT_PLAN_MODE_TOOL = "exit_plan_mode"
APPROVAL_TOOLS = {"run_shell", "run_code", "write_file", "edit_file"}
# Read / search tools never require approval
SAFE_TOOLS = {
    "glob",
    "grep",
    "list_dir",
    "read_file",
    "kb_search",
    "kb_read",
    "kb_get",
    "kb_list",
    "kb_sync_docs",
    "kb_stats",
    "kb_reindex",
    "weknora_search",
    "weknora_list_kbs",
    "weknora_health",
    "weknora_read",
    "web_search",
    "literature_search",
    "image_search",
    "web_crawl",
    "todo_write",
    "open_canvas",
    "ask_user",
    "exit_plan_mode",
}
PLAN_ALLOWED_TOOLS = {
    "glob",
    "grep",
    "list_dir",
    "read_file",
    "ask_user",
    "exit_plan_mode",
    "open_canvas",
    "kb_search",
    "kb_read",
    "kb_get",
    "kb_list",
    "kb_stats",
    "web_search",
    "literature_search",
    "image_search",
    "web_crawl",
    "weknora_search",
    "weknora_list_kbs",
    "weknora_health",
    "weknora_read",
}


def _merge_tool_call_deltas(
    acc: Dict[int, Dict[str, Any]],
    deltas: List[Dict[str, Any]],
) -> None:
    for item in deltas or []:
        idx = int(item.get("index", 0))
        slot = acc.setdefault(
            idx,
            {"id": "", "type": "function", "function": {"name": "", "arguments": ""}},
        )
        if item.get("id"):
            slot["id"] = item["id"]
        fn = item.get("function") or {}
        if fn.get("name"):
            slot["function"]["name"] = fn["name"]
        if fn.get("arguments"):
            slot["function"]["arguments"] += fn["arguments"]


def _trim_tool_payload(obj: Any, limit: int = 24000) -> Any:
    # Keep write_file pre-images usable for DiffDock reject (cap previous alone).
    if isinstance(obj, dict) and "previous" in obj:
        out = {k: v for k, v in obj.items() if k != "previous"}
        prev = obj.get("previous")
        if isinstance(prev, str):
            if len(prev) > 120_000:
                out["previous"] = prev[:120_000]
                out["previous_truncated"] = True
            else:
                out["previous"] = prev
        try:
            raw = json.dumps(out, ensure_ascii=False, default=str)
        except TypeError:
            raw = str(out)
        if len(raw) <= max(limit, 160_000):
            return out
        out.pop("previous", None)
        out["previous_omitted"] = True
        return out
    try:
        raw = json.dumps(obj, ensure_ascii=False, default=str)
    except TypeError:
        raw = str(obj)
    if len(raw) <= limit:
        return obj
    return {"truncated": True, "preview": raw[:limit] + "\n…[truncated]"}


def _resolve_plugin_tool(plugins: PluginManager, tool_map: Dict[str, Any], name: str):
    plugin_id, tool_name = tool_map.get(name, (None, name))
    if plugin_id:
        p = plugins.plugins.get(plugin_id)
        if p is not None and p.state.value == "ready":
            return plugin_id, tool_name
        return None, name
    # Only resolve against READY plugins — disabled tools must not linger.
    for p in plugins.plugins.values():
        if p.state.value != "ready":
            continue
        for t in p.manifest.tools or []:
            if t.get("name") == name:
                return p.plugin_id, name
    return None, name


def _parse_args(raw: str) -> Dict[str, Any]:
    text = (raw or "").strip() or "{}"
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {"value": data}
    except json.JSONDecodeError:
        return {"raw": text}


def _extract_usage(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Normalize provider usage; preserve cache-hit fields when present."""
    empty = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "cached_tokens": 0,
        "cache_creation_tokens": 0,
    }
    if not raw:
        return dict(empty)
    prompt = int(raw.get("prompt_tokens") or raw.get("input_tokens") or 0)
    completion = int(raw.get("completion_tokens") or raw.get("output_tokens") or 0)
    total = int(raw.get("total_tokens") or (prompt + completion))

    cached = 0
    created = 0
    details = raw.get("prompt_tokens_details") or raw.get("input_tokens_details") or {}
    if isinstance(details, dict):
        cached = int(details.get("cached_tokens") or details.get("cache_read_tokens") or 0)
        created = int(details.get("cache_creation_tokens") or details.get("cache_write_tokens") or 0)
    cached = int(
        raw.get("cached_tokens")
        or raw.get("prompt_cache_hit_tokens")
        or raw.get("cache_read_input_tokens")
        or cached
        or 0
    )
    created = int(
        raw.get("cache_creation_tokens")
        or raw.get("prompt_cache_miss_tokens")
        or raw.get("cache_creation_input_tokens")
        or created
        or 0
    )

    out: Dict[str, Any] = {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total,
        "cached_tokens": cached,
        "cache_creation_tokens": created,
    }
    if raw.get("estimated"):
        out["estimated"] = 1
    if raw.get("duration_ms") is not None:
        try:
            out["duration_ms"] = float(raw.get("duration_ms") or 0)
        except (TypeError, ValueError):
            pass
    return out


def _add_usage(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    prompt = int(a.get("prompt_tokens") or 0) + int(b.get("prompt_tokens") or 0)
    completion = int(a.get("completion_tokens") or 0) + int(b.get("completion_tokens") or 0)
    cached = int(a.get("cached_tokens") or 0) + int(b.get("cached_tokens") or 0)
    created = int(a.get("cache_creation_tokens") or 0) + int(b.get("cache_creation_tokens") or 0)
    out: Dict[str, Any] = {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": prompt + completion,
        "cached_tokens": cached,
        "cache_creation_tokens": created,
    }
    if a.get("estimated") or b.get("estimated"):
        out["estimated"] = 1
    dur_a = float(a.get("duration_ms") or 0)
    dur_b = float(b.get("duration_ms") or 0)
    if dur_a or dur_b:
        out["duration_ms"] = dur_a + dur_b
    return out


def estimate_usage(messages: List[ChatMessage], output: str) -> Dict[str, Any]:
    prompt_chars = sum(len(m.content or "") for m in messages)
    prompt = max(1, (prompt_chars + 3) // 4) if prompt_chars else 0
    completion = max(1, (len(output or "") + 3) // 4) if output else 0
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": prompt + completion,
        "cached_tokens": 0,
        "cache_creation_tokens": 0,
        "estimated": 1,
    }


def _tool_short_name(name: str) -> str:
    n = (name or "").strip()
    if "." in n:
        n = n.rsplit(".", 1)[-1]
    return n


def _known_short_tools() -> set:
    return (
        SUBAGENT_ALL
        | APPROVAL_TOOLS
        | PLAN_ALLOWED_TOOLS
        | {ASK_USER_TOOL, TODO_WRITE_TOOL, OPEN_CANVAS_TOOL, EXIT_PLAN_MODE_TOOL}
    )


def _filter_openai_tools(
    tools: List[Dict[str, Any]],
    allow_subagents: bool,
    *,
    agent_mode: str = "agent",
    plan_enforcement: str = "hard",
    permission_preset: str = "workspace-write",
    active_tools: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    from src.common.permission_presets import (
        MUTATING_TOOLS,
        blocks_mutating_tools,
        plan_hard_enforcement,
    )

    out = []
    plan = agent_mode == "plan" and plan_hard_enforcement(plan_enforcement)
    readonly = blocks_mutating_tools(permission_preset)
    active_set = {str(t).strip() for t in (active_tools or []) if str(t).strip()} or None
    for t in tools:
        name = ((t.get("function") or {}).get("name") or "")
        base = _base_tool_name(name)
        leaf = _tool_leaf_name(base)
        if not allow_subagents and base in SUBAGENT_ALL:
            continue
        if plan and base not in PLAN_ALLOWED_TOOLS:
            continue
        if readonly and (base in MUTATING_TOOLS or leaf in MUTATING_TOOLS):
            continue
        if active_set is not None:
            if name not in active_set and base not in active_set and leaf not in active_set:
                # Keep essential control tools even when subset is active
                if leaf not in {"ask_user", "exit_plan_mode", "todo_write"}:
                    continue
        out.append(t)
    return out


def _base_tool_name(name: str) -> str:
    # Accept both short and prefixed forms
    raw = name or ""
    known = _known_short_tools()
    if raw in known:
        return raw
    for short in known:
        if raw.endswith("_" + short) or raw.endswith("." + short) or raw == short:
            return short
    if "." in raw:
        return raw.rsplit(".", 1)[-1]
    return raw


def _tool_leaf_name(name: str) -> str:
    """Normalize plugin / OpenAI tool ids to a short leaf for approval checks."""
    b = (name or "").strip().lower()
    if not b:
        return ""
    if "." in b:
        b = b.rsplit(".", 1)[-1]
    for prefix in ("builtin_workspace_", "builtin_subagent_", "builtin_", "cli_"):
        if b.startswith(prefix):
            b = b[len(prefix) :]
            break
    return b


def _requires_approval(base: str) -> bool:
    """Mutating tools need UI approval unless Accept / auto_accept is on."""
    b = (base or "").strip().lower()
    if not b:
        return False
    leaf = _tool_leaf_name(b)
    if leaf in SAFE_TOOLS or b in SAFE_TOOLS:
        return False
    if leaf in APPROVAL_TOOLS or b in APPROVAL_TOOLS:
        return True
    # Exact leaf match only — avoid substring false positives like preview_write_file_diff.
    mutating = {
        "write_file",
        "edit_file",
        "run_shell",
        "apply_patch",
        "str_replace",
        "create_file",
        "bash",
        "shell",
        "terminal",
        "exec",
    }
    if leaf in mutating:
        return True
    return False


async def run_agent_stream(
    *,
    gateway: ModelGateway,
    plugins: PluginManager,
    messages: List[ChatMessage],
    provider: Optional[str],
    model: Optional[str],
    tools_enabled: bool,
    task_id: Optional[str] = None,
    max_rounds: int = 6,
    workspace_cwd: Optional[str] = None,
    workspace_meta: Optional[Dict[str, Any]] = None,
    allow_subagents: bool = True,
    cancel_event: Optional[asyncio.Event] = None,
    event_prefix: Optional[Dict[str, Any]] = None,
    parent_session_id: Optional[str] = None,
) -> AsyncIterator[Dict[str, Any]]:
    """Yield SSE-friendly dicts: notice / delta / tool_call / tool_result / subagent / done / error."""
    from src.common.config import get_settings

    settings = get_settings()
    rounds = int(max_rounds or 0) or int(settings.agent_max_rounds)
    if workspace_cwd:
        rounds = max(rounds, int(settings.agent_max_rounds_workspace))
    meta = dict(workspace_meta or {})
    session_id = parent_session_id or str(meta.get("session_id") or "")
    with workspace_cwd_scope(workspace_cwd, meta):
        async for chunk in _run_agent_stream_inner(
            gateway=gateway,
            plugins=plugins,
            messages=messages,
            provider=provider,
            model=model,
            tools_enabled=tools_enabled,
            task_id=task_id,
            max_rounds=rounds,
            workspace_cwd=workspace_cwd,
            workspace_meta=meta,
            allow_subagents=allow_subagents,
            cancel_event=cancel_event,
            parent_session_id=session_id,
        ):
            yield chunk


async def _run_agent_stream_inner(
    *,
    gateway: ModelGateway,
    plugins: PluginManager,
    messages: List[ChatMessage],
    provider: Optional[str],
    model: Optional[str],
    tools_enabled: bool,
    task_id: Optional[str] = None,
    max_rounds: int = 4,
    workspace_cwd: Optional[str] = None,
    workspace_meta: Optional[Dict[str, Any]] = None,
    allow_subagents: bool = True,
    cancel_event: Optional[asyncio.Event] = None,
    parent_session_id: str = "",
) -> AsyncIterator[Dict[str, Any]]:
    working = list(messages)
    meta0 = dict(workspace_meta or {})
    agent_mode = str(meta0.get("agent_mode") or "agent").strip().lower()
    if agent_mode not in ("agent", "plan"):
        agent_mode = "agent"
    from src.common.permission_presets import (
        MUTATING_TOOLS,
        blocks_mutating_tools,
        effective_auto_accept,
        normalize_preset,
        plan_hard_enforcement,
    )

    permission_preset = normalize_preset(meta0.get("permission_preset"))
    plan_enforcement = str(meta0.get("plan_enforcement") or "hard").strip().lower()
    from src.common.experience_tiers import normalize_reasoning_effort

    reasoning_effort = normalize_reasoning_effort(meta0.get("reasoning_effort"))
    auto_accept = effective_auto_accept(
        permission_preset=permission_preset,
        auto_accept=meta0.get("auto_accept"),
    )

    # Dynamic tool subset: session active_tools > skill allowed-tools > extension registry
    from src.core_kernel.extension_runtime import (
        discover_and_load_extensions,
        emit_extension_event,
        get_extension_registry,
        invoke_extension_tool,
        lookup_extension_tool,
        run_tool_call_hooks,
    )
    from src.core_kernel.skills_loader import active_skill_allowed_tools

    ext_reg = discover_and_load_extensions(workspace_cwd or meta0.get("cwd"), reload=False)
    active_tools: Optional[List[str]] = None
    raw_active = meta0.get("active_tools")
    if isinstance(raw_active, list) and raw_active:
        active_tools = [str(x) for x in raw_active if str(x).strip()]
    else:
        # Infer from latest user message /skill:…
        last_user = ""
        for m in reversed(working):
            role = getattr(m, "role", None)
            role_s = role.value if hasattr(role, "value") else str(role or "")
            if role_s == "user":
                last_user = str(getattr(m, "content", "") or "")
                break
        skill_tools = active_skill_allowed_tools(
            workspace_cwd or meta0.get("cwd"), last_user
        )
        if skill_tools:
            active_tools = skill_tools
            emit_extension_event(
                "before_agent_start",
                {"active_tools": active_tools, "via": "skill", "session_id": parent_session_id},
            )
        else:
            reg_active = ext_reg.get_active_tools()
            if reg_active:
                active_tools = reg_active

    def _assemble_tools() -> List[Dict[str, Any]]:
        base_tools = plugins.as_openai_tools()
        # Merge extension-registered tools
        ext_tools = get_extension_registry().as_openai_extension_tools()
        if ext_tools:
            names = {
                ((t.get("function") or {}).get("name") or "")
                for t in base_tools
            }
            for t in ext_tools:
                n = ((t.get("function") or {}).get("name") or "")
                if n and n not in names:
                    base_tools.append(t)
        filtered = _filter_openai_tools(
            base_tools,
            allow_subagents,
            agent_mode=agent_mode,
            plan_enforcement=plan_enforcement,
            permission_preset=permission_preset,
            active_tools=active_tools,
        )
        return get_extension_registry().filter_openai_tools(filtered)

    openai_tools = _assemble_tools() if tools_enabled else []
    tool_map = plugins.tool_name_map() if tools_enabled else {}
    usage_total: Dict[str, Any] = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "cached_tokens": 0,
        "cache_creation_tokens": 0,
    }
    last_collected = ""
    depth = int((workspace_meta or {}).get("subagent_depth") or 0)
    turn_started = time.perf_counter()

    emit_extension_event(
        "before_agent_start",
        {
            "session_id": parent_session_id,
            "agent_mode": agent_mode,
            "active_tools": active_tools,
            "tool_count": len(openai_tools),
        },
    )
    # Surface active-tool subset in trajectory for auditability
    if active_tools:
        yield {
            "delta": "",
            "done": False,
            "notice": f"active tools ({len(active_tools)}): {', '.join(active_tools[:24])}",
            "notice_kind": "active_tools",
            "active_tools": list(active_tools),
        }

    # Latest user message → extension bus
    for m in reversed(working):
        role = getattr(m, "role", None)
        role_s = role.value if hasattr(role, "value") else str(role or "")
        if role_s == "user":
            emit_extension_event(
                "user_message",
                {
                    "session_id": parent_session_id,
                    "content": str(getattr(m, "content", "") or "")[:4000],
                },
            )
            break

    def _stamp_usage() -> Dict[str, Any]:
        out = dict(usage_total)
        out["duration_ms"] = (time.perf_counter() - turn_started) * 1000
        return out

    def _finish_turn(payload: Dict[str, Any]) -> Dict[str, Any]:
        emit_extension_event(
            "after_agent_turn",
            {
                "session_id": parent_session_id,
                "error": payload.get("error"),
                "cancelled": payload.get("cancelled"),
                "usage": payload.get("usage"),
                "active_tools": active_tools,
            },
        )
        return payload

    def _refresh_tools() -> None:
        nonlocal openai_tools, tool_map, active_tools
        if not tools_enabled:
            openai_tools = []
            tool_map = {}
            return
        # Refresh subset from registry (extensions may change mid-turn)
        reg_active = get_extension_registry().get_active_tools()
        if reg_active is not None:
            active_tools = reg_active
        openai_tools = _assemble_tools()
        tool_map = plugins.tool_name_map()

    for round_i in range(max_rounds):
        if cancel_event and cancel_event.is_set():
            yield _finish_turn(
                {
                    "delta": "",
                    "done": True,
                    "content": last_collected,
                    "usage": _stamp_usage(),
                    "error": "interrupted",
                    "cancelled": True,
                }
            )
            return

        # Mid-turn steer: claim inbox steers before each model step.
        sid = str(parent_session_id or (workspace_meta or {}).get("session_id") or "").strip()
        if sid:
            try:
                from src.common.session_inbox import claim_kind

                broker = workspace_meta.get("_session_broker") if workspace_meta else None
                if broker is None:
                    from src.common.config import get_settings
                    from src.infrastructure.redis_client import create_broker

                    broker = create_broker(get_settings())
                    await broker.connect()
                    if workspace_meta is not None:
                        workspace_meta["_session_broker"] = broker
                session = await broker.get_session(sid)
                if session:
                    holder: dict = {"claimed": []}

                    def mutate(sess: dict) -> None:
                        holder["claimed"] = claim_kind(sess, "steer")

                    # Only mutate inbox — never rewrite messages (orchestrator
                    # appends tool/assistant rows concurrently on Redis).
                    await broker.update_session(sid, mutate, preserve_messages=True)
                    claimed = holder["claimed"]
                    if claimed:
                        for item in claimed:
                            text = str(item.get("content") or "").strip()
                            if not text:
                                continue
                            working.append(
                                ChatMessage(
                                    role=ChatRole.USER,
                                    content=text,
                                    metadata={
                                        "kind": "inbox_steer",
                                        "inbox_id": item.get("id"),
                                    },
                                )
                            )
                        yield {"delta": "", "done": False, "inbox_claimed": claimed}
            except Exception:
                # Inbox is best-effort; never fail the agent turn for it.
                pass

        _refresh_tools()
        from src.core_kernel.compaction_summarizer import compact_messages_async
        from src.core_kernel.tool_hooks import run_post_compact_hook, run_pre_compact_hook

        pre_compact = run_pre_compact_hook(
            session_id=parent_session_id,
            cwd=workspace_cwd or meta0.get("cwd"),
            model=model,
            message_count=len(working),
        )
        emit_extension_event(
            "pre_compact",
            {
                "session_id": parent_session_id,
                "model": model,
                "message_count": len(working),
                **(pre_compact if isinstance(pre_compact, dict) else {}),
            },
        )
        skip_compact = bool(pre_compact.get("skip")) if isinstance(pre_compact, dict) else False
        extra_instructions = ""
        if isinstance(pre_compact, dict):
            extra_instructions = str(pre_compact.get("instructions") or "")
        if skip_compact:
            compact_info = {}
        else:
            working, compact_info = await compact_messages_async(
                working,
                model_name=model,
                gateway=gateway,
                provider=provider,
                task_id=task_id,
                use_llm=True,
            )
        if extra_instructions and compact_info.get("compacted_via"):
            compact_info = {**compact_info, "hook_instructions": extra_instructions}
        if compact_info.get("compacted_via"):
            from src.core_kernel.compaction_ledger import make_compaction_entry, notice_from_info

            entry = make_compaction_entry(compact_info)
            emit_extension_event("compaction", {"session_id": parent_session_id, **entry})
            run_post_compact_hook(
                session_id=parent_session_id,
                cwd=workspace_cwd or meta0.get("cwd"),
                compact_info=compact_info,
            )
            emit_extension_event(
                "post_compact",
                {"session_id": parent_session_id, **entry},
            )
            yield {
                "delta": "",
                "done": False,
                "notice": notice_from_info(compact_info),
                "notice_kind": "compaction",
                "compaction": entry,
            }
        if round_i == 0 and depth <= 0:
            try:
                from src.core_kernel.kb_grounding import apply_turn_grounding

                if parent_session_id and not meta0.get("session_id"):
                    meta0["session_id"] = parent_session_id
                working, ground_ev = await apply_turn_grounding(working, meta0)
                if ground_ev:
                    yield ground_ev
            except Exception:
                pass
        from src.core_kernel.tool_history import sanitize_tool_call_messages

        working = sanitize_tool_call_messages(working)
        req = ModelRequest(
            provider=provider,
            model=model,
            messages=working,
            tools=openai_tools or None,
            stream=True,
            reasoning_effort=reasoning_effort,
        )
        emit_extension_event(
            "model_request",
            {
                "session_id": parent_session_id,
                "provider": provider,
                "model": model,
                "round": round_i,
                "tool_count": len(openai_tools or []),
            },
        )
        collected = ""
        tool_acc: Dict[int, Dict[str, Any]] = {}
        round_usage: Dict[str, Any] = {}
        overflow_retried = False

        while True:
            collected = ""
            tool_acc = {}
            round_usage = {}
            stream_failed: Optional[BaseException] = None
            try:
                async for chunk in gateway.stream(req, task_id=task_id):
                    if cancel_event and cancel_event.is_set():
                        break
                    if chunk.notice:
                        yield {
                            "delta": "",
                            "done": False,
                            "notice": chunk.notice,
                            "retry_attempt": chunk.retry_attempt,
                            "retry_wait_seconds": chunk.retry_wait_seconds,
                        }
                        continue
                    if chunk.content:
                        collected += chunk.content
                        yield {"delta": chunk.content, "done": False}
                    if getattr(chunk, "reasoning", None):
                        yield {"delta": "", "done": False, "reasoning_delta": chunk.reasoning}
                    if chunk.tool_calls:
                        _merge_tool_call_deltas(tool_acc, chunk.tool_calls)
                    if chunk.usage:
                        round_usage = _extract_usage(chunk.usage)
            except BaseException as exc:
                stream_failed = exc

            if stream_failed is not None:
                from src.core_kernel.context_overflow import is_context_overflow_error

                if not overflow_retried and is_context_overflow_error(stream_failed):
                    overflow_retried = True
                    yield {
                        "delta": "",
                        "done": False,
                        "notice": "上下文溢出，正在强力压缩后重试…",
                    }
                    working, compact_info = await compact_messages_async(
                        working,
                        model_name=model,
                        gateway=gateway,
                        provider=provider,
                        task_id=task_id,
                        use_llm=True,
                        aggressiveness="aggressive",
                    )
                    # Extra hard shrink if still large after aggressive profile.
                    from src.core_kernel.context_compact import (
                        compact_messages,
                        resolve_context_window,
                    )

                    win = resolve_context_window(model)
                    working = compact_messages(
                        working,
                        model_name=model,
                        context_window=max(8_000, int(win * 0.45)),
                        aggressiveness="aggressive",
                    )
                    if compact_info.get("compacted_via"):
                        from src.core_kernel.compaction_ledger import make_compaction_entry

                        yield {
                            "delta": "",
                            "done": False,
                            "notice": "溢出恢复压缩完成，重试模型调用",
                            "notice_kind": "compaction",
                            "compaction": make_compaction_entry(compact_info),
                        }
                    from src.core_kernel.tool_history import sanitize_tool_call_messages

                    working = sanitize_tool_call_messages(working)
                    req = ModelRequest(
                        provider=provider,
                        model=model,
                        messages=working,
                        tools=openai_tools or None,
                        stream=True,
                        reasoning_effort=reasoning_effort,
                    )
                    continue
                raise stream_failed
            break

        if cancel_event and cancel_event.is_set():
            yield _finish_turn(
                {
                    "delta": "",
                    "done": True,
                    "content": collected or last_collected,
                    "usage": _stamp_usage(),
                    "error": "interrupted",
                    "cancelled": True,
                }
            )
            return

        last_collected = collected
        if round_usage.get("total_tokens"):
            usage_total = _add_usage(usage_total, round_usage)
        else:
            usage_total = _add_usage(usage_total, estimate_usage(working, collected))
        emit_extension_event(
            "model_response",
            {
                "session_id": parent_session_id,
                "round": round_i,
                "content_len": len(collected or ""),
                "had_tool_calls": bool(tool_acc),
                "usage": dict(round_usage) if round_usage else {},
            },
        )

        finalized = [tool_acc[i] for i in sorted(tool_acc.keys())] if tool_acc else []
        if not finalized:
            # Weak models often print "web_search\n{...}" instead of API tool_calls — recover.
            from src.core_kernel.pseudo_tools import extract_pseudo_tool_calls, strip_pseudo_tool_text

            recovered = extract_pseudo_tool_calls(collected)
            if recovered:
                finalized = recovered
                collected = strip_pseudo_tool_text(collected)
                yield {
                    "delta": "",
                    "done": False,
                    "notice": "已将正文中的伪工具调用转为真实调用",
                }
        if not finalized:
            out = {
                "delta": "",
                "done": True,
                "content": collected,
                "usage": _stamp_usage(),
            }
            if agent_mode == "plan" and (collected or "").strip():
                out["plan_ready"] = True
            yield _finish_turn(out)
            return

        working.append(
            ChatMessage(
                role=ChatRole.ASSISTANT,
                content=collected or "",
                metadata={"tool_calls": finalized},
            )
        )

        pending: List[Dict[str, Any]] = []
        for i, tc in enumerate(finalized):
            fn = tc.get("function") or {}
            name = fn.get("name") or ""
            call_id = tc.get("id") or f"call_{round_i}_{i}_{name}"
            args = _parse_args(fn.get("arguments") or "")
            base = _base_tool_name(name)
            tool_payload = {
                "id": call_id,
                "name": name,
                "arguments": args,
                "raw_arguments": fn.get("arguments") or "",
            }
            if base in SUBAGENT_STREAM_TOOLS:
                tool_payload["kind"] = "subagent"
                tool_payload["subagent_mode"] = (
                    "fork" if base == "subagent_fork" else ("message" if base == "send_message" else "spawn")
                )
            if base == ASK_USER_TOOL:
                tool_payload["kind"] = "ask_user"
            if base == TODO_WRITE_TOOL:
                tool_payload["kind"] = "todo"
            if base == EXIT_PLAN_MODE_TOOL:
                tool_payload["kind"] = "plan_review"
            yield {"delta": "", "done": False, "tool_call": tool_payload}
            pending.append({"call_id": call_id, "name": name, "base": base, "args": args})

        stream_items = [p for p in pending if p["base"] in SUBAGENT_STREAM_TOOLS]
        ask_items = [p for p in pending if p["base"] == ASK_USER_TOOL]
        exit_plan_items = [p for p in pending if p["base"] == EXIT_PLAN_MODE_TOOL]
        other_items = [
            p
            for p in pending
            if p["base"] not in SUBAGENT_STREAM_TOOLS
            and p["base"] != ASK_USER_TOOL
            and p["base"] != EXIT_PLAN_MODE_TOOL
        ]

        def _append_tool_result(payload: Dict[str, Any]) -> None:
            working.append(
                ChatMessage(
                    role=ChatRole.TOOL,
                    content=json.dumps(
                        {"ok": payload["success"], "result": payload["result"], "error": payload["error"]},
                        ensure_ascii=False,
                        default=str,
                    ),
                    name=payload["name"],
                    tool_call_id=payload["id"],
                    metadata={
                        "plugin_id": payload.get("plugin_id"),
                        "duration_ms": payload.get("duration_ms"),
                        "kind": payload.get("kind"),
                    },
                )
            )

        async def _invoke_tool(item: Dict[str, Any]) -> Dict[str, Any]:
            name = item["name"]
            call_id = item["call_id"]
            args = dict(item["args"])
            base = item["base"]
            t0 = time.perf_counter()

            if (
                agent_mode == "plan"
                and plan_hard_enforcement(plan_enforcement)
                and base not in PLAN_ALLOWED_TOOLS
            ):
                return {
                    "id": call_id,
                    "name": name,
                    "plugin_id": None,
                    "success": False,
                    "result": None,
                    "error": f"plan mode forbids tool `{base}`; accept the plan first",
                    "duration_ms": 0,
                    "kind": "blocked",
                }

            if blocks_mutating_tools(permission_preset) and (
                base in MUTATING_TOOLS or _tool_leaf_name(base) in MUTATING_TOOLS
            ):
                return {
                    "id": call_id,
                    "name": name,
                    "plugin_id": None,
                    "success": False,
                    "result": None,
                    "error": f"permission preset `read-only` forbids tool `{base}`",
                    "duration_ms": 0,
                    "kind": "blocked",
                }

            plugin_id, tool_name = _resolve_plugin_tool(plugins, tool_map, name)
            if base in SUBAGENT_CONTROL_TOOLS:
                args["_parent_session_id"] = parent_session_id
            if not plugin_id:
                ext = lookup_extension_tool(name) or lookup_extension_tool(base)
                if ext:
                    plugin_id = f"extension.{ext.get('_extension') or 'anon'}"
                    tool_name = name
            if not plugin_id:
                return {
                    "id": call_id,
                    "name": name,
                    "plugin_id": None,
                    "success": False,
                    "result": None,
                    "error": f"unknown tool: {name}",
                    "duration_ms": (time.perf_counter() - t0) * 1000,
                }

            from src.core_kernel.tool_hooks import run_pre_tool_hook

            hook = run_pre_tool_hook(
                tool=name,
                base=base,
                arguments=args,
                plugin_id=plugin_id,
                session_id=parent_session_id,
                task_id=task_id,
                cwd=workspace_cwd or meta0.get("cwd"),
            )
            if hook.get("block"):
                return {
                    "id": call_id,
                    "name": name,
                    "plugin_id": plugin_id,
                    "success": False,
                    "result": None,
                    "error": str(hook.get("reason") or "blocked by pre_tool hook"),
                    "duration_ms": (time.perf_counter() - t0) * 1000,
                    "kind": "blocked",
                }
            if isinstance(hook.get("arguments"), dict):
                args = dict(hook["arguments"])

            # Extension event bus (tool_call) — may block or transform args / shell spawn
            ext_hook = run_tool_call_hooks(
                {
                    "tool": name,
                    "base": base,
                    "arguments": dict(args),
                    "plugin_id": plugin_id,
                    "session_id": parent_session_id,
                    "task_id": task_id,
                    "cwd": workspace_cwd or meta0.get("cwd") or "",
                }
            )
            if ext_hook.get("block"):
                return {
                    "id": call_id,
                    "name": name,
                    "plugin_id": plugin_id,
                    "success": False,
                    "result": None,
                    "error": str(ext_hook.get("reason") or "blocked by extension"),
                    "duration_ms": (time.perf_counter() - t0) * 1000,
                    "kind": "blocked",
                }
            if isinstance(ext_hook.get("arguments"), dict):
                args = dict(ext_hook["arguments"])
            # Bash spawn-hook transforms
            if base == "run_shell":
                if ext_hook.get("command") is not None:
                    args["command"] = ext_hook["command"]
                if ext_hook.get("cwd") is not None:
                    args["cwd"] = ext_hook["cwd"]
                if isinstance(ext_hook.get("env"), dict):
                    env = dict(args.get("env") or {})
                    env.update(ext_hook["env"])
                    args["env"] = env

            timeout = 60.0
            if base == "run_shell":
                try:
                    timeout = float(args.get("timeout_seconds") or 60)
                except (TypeError, ValueError):
                    timeout = 60.0
            if str(plugin_id).startswith("extension."):
                ext_out = await invoke_extension_tool(tool_name, args)
                from src.common.schemas import PluginInvokeResult

                result = PluginInvokeResult(
                    plugin_id=plugin_id,
                    tool_name=tool_name,
                    success=bool(ext_out.get("ok", True)) and not ext_out.get("error"),
                    result=ext_out.get("result", ext_out),
                    error=ext_out.get("error"),
                    duration_ms=float(ext_out.get("duration_ms") or (time.perf_counter() - t0) * 1000),
                )
            else:
                result = await plugins.invoke(
                    PluginInvokeRequest(
                        plugin_id=plugin_id,
                        tool_name=tool_name,
                        arguments=args,
                        timeout_seconds=timeout,
                    ),
                    task_id=task_id,
                )
            emit_extension_event(
                "tool_result",
                {
                    "tool": name,
                    "base": base,
                    "success": result.success,
                    "session_id": parent_session_id,
                    "task_id": task_id,
                },
            )
            return {
                "id": call_id,
                "name": name,
                "plugin_id": plugin_id,
                "success": result.success,
                "result": _trim_tool_payload(result.result),
                "error": result.error,
                "duration_ms": result.duration_ms,
            }

        safe_items = [
            p for p in other_items if auto_accept or not _requires_approval(p["base"])
        ]
        risky_items = [
            p for p in other_items if (not auto_accept) and _requires_approval(p["base"])
        ]

        if safe_items:
            from src.common.config import get_settings

            max_parallel = max(1, int(get_settings().agent_max_parallel_tool_calls or 8))
            for offset in range(0, len(safe_items), max_parallel):
                batch = safe_items[offset : offset + max_parallel]
                payloads = await asyncio.gather(*[_invoke_tool(item) for item in batch])
                for payload, item in zip(payloads, batch):
                    if item["base"] == TODO_WRITE_TOOL and payload.get("success"):
                        payload = {**payload, "kind": "todo"}
                        items = ((payload.get("result") or {}) if isinstance(payload.get("result"), dict) else {}).get(
                            "items"
                        ) or []
                        yield {
                            "delta": "",
                            "done": False,
                            "todos": {"items": items, "call_id": payload.get("id")},
                        }
                    if item["base"] == OPEN_CANVAS_TOOL and payload.get("success"):
                        result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
                        payload = {**payload, "kind": "canvas"}
                        yield {
                            "delta": "",
                            "done": False,
                            "canvas_open": {
                                "kind": result.get("kind") or "markdown",
                                "title": result.get("title") or "Canvas",
                                "body": result.get("body") or "",
                                "dedupeKey": result.get("dedupe_key") or result.get("path") or "",
                                "path": result.get("path") or "",
                                "call_id": payload.get("id"),
                            },
                        }
                    yield {"delta": "", "done": False, "tool_result": payload}
                    _append_tool_result(payload)

        for item in risky_items:
            if cancel_event and cancel_event.is_set():
                break
            if auto_accept:
                payload = await _invoke_tool(item)
                yield {"delta": "", "done": False, "tool_result": payload}
                _append_tool_result(payload)
                continue
            approval_payload = {
                "id": item["call_id"],
                "call_id": item["call_id"],
                "name": item["name"],
                "base": item["base"],
                "arguments": item["args"],
                "session_id": parent_session_id,
            }
            yield {"delta": "", "done": False, "tool_approval": approval_payload}
            await user_gate.open_gate(
                item["call_id"],
                session_id=parent_session_id,
                kind="approval",
                meta=approval_payload,
            )
            from src.common.approval_timeouts import approval_timeout_seconds

            decision = await user_gate.await_gate(
                item["call_id"],
                timeout=approval_timeout_seconds(item.get("base") or item.get("name")),
            )
            if cancel_event and cancel_event.is_set():
                payload = {
                    "id": item["call_id"],
                    "name": item["name"],
                    "plugin_id": None,
                    "success": False,
                    "result": None,
                    "error": "interrupted",
                    "duration_ms": 0,
                    "kind": "denied",
                }
                yield {"delta": "", "done": False, "tool_result": payload}
                _append_tool_result(payload)
                break
            action = str((decision or {}).get("action") or "deny").lower()
            # allow_session / always: skip further gates THIS turn; client also
            # sets Accept (auto_accept) so subsequent requests send auto_accept=true.
            if action in ("allow_session", "always"):
                auto_accept = True
                action = "allow"
            if action != "allow":
                payload = {
                    "id": item["call_id"],
                    "name": item["name"],
                    "plugin_id": None,
                    "success": False,
                    "result": None,
                    "error": f"user denied tool `{item['base']}`: {(decision or {}).get('reason') or 'denied'}",
                    "duration_ms": 0,
                    "kind": "denied",
                }
                yield {"delta": "", "done": False, "tool_result": payload}
                _append_tool_result(payload)
                continue
            payload = await _invoke_tool(item)
            yield {"delta": "", "done": False, "tool_result": payload}
            _append_tool_result(payload)

        for item in ask_items:
            if cancel_event and cancel_event.is_set():
                break
            args = dict(item["args"])
            questions = args.get("questions") or []
            if not isinstance(questions, list):
                questions = []
            if not questions and args.get("prompt"):
                questions = [
                    {
                        "id": "q1",
                        "prompt": args.get("prompt"),
                        "options": args.get("options") or [],
                        "allow_multiple": bool(args.get("allow_multiple")),
                        "allow_custom": bool(args.get("allow_custom", True)),
                    }
                ]
            ask_payload = {
                "id": item["call_id"],
                "name": item["name"],
                "title": args.get("title") or "需要你的确认",
                "questions": questions,
                "session_id": parent_session_id,
            }
            yield {"delta": "", "done": False, "ask_user": ask_payload}
            await user_gate.open_gate(
                item["call_id"],
                session_id=parent_session_id,
                kind="ask_user",
                meta=ask_payload,
            )
            decision = await user_gate.await_gate(item["call_id"], timeout=900.0)
            action = str((decision or {}).get("action") or "submit").lower()
            if action == "deny":
                payload = {
                    "id": item["call_id"],
                    "name": item["name"],
                    "plugin_id": "builtin.workspace",
                    "success": False,
                    "result": None,
                    "error": (decision or {}).get("reason") or "user dismissed ask_user",
                    "duration_ms": 0,
                    "kind": "ask_user",
                }
            else:
                answers = (decision or {}).get("answers")
                if answers is None:
                    answers = decision
                payload = {
                    "id": item["call_id"],
                    "name": item["name"],
                    "plugin_id": "builtin.workspace",
                    "success": True,
                    "result": {"answers": answers},
                    "error": None,
                    "duration_ms": 0,
                    "kind": "ask_user",
                }
            yield {"delta": "", "done": False, "tool_result": payload}
            _append_tool_result(payload)

        for item in exit_plan_items:
            if cancel_event and cancel_event.is_set():
                break
            args = dict(item["args"])
            plan_text = str(args.get("plan") or "").strip()
            if agent_mode != "plan":
                payload = {
                    "id": item["call_id"],
                    "name": item["name"],
                    "plugin_id": "builtin.workspace",
                    "success": False,
                    "result": None,
                    "error": "exit_plan_mode is only available in plan mode",
                    "duration_ms": 0,
                    "kind": "plan_review",
                }
                yield {"delta": "", "done": False, "tool_result": payload}
                _append_tool_result(payload)
                continue
            if not plan_text or not plan_text.lstrip().startswith("#"):
                payload = {
                    "id": item["call_id"],
                    "name": item["name"],
                    "plugin_id": "builtin.workspace",
                    "success": False,
                    "result": None,
                    "error": (
                        "exit_plan_mode requires a non-empty markdown plan starting with a # heading"
                    ),
                    "duration_ms": 0,
                    "kind": "plan_review",
                }
                yield {"delta": "", "done": False, "tool_result": payload}
                _append_tool_result(payload)
                continue

            review_payload = {
                "id": item["call_id"],
                "name": item["name"],
                "title": "Plan review",
                "plan": plan_text,
                "session_id": parent_session_id,
                "kind": "plan_review",
            }
            yield {"delta": "", "done": False, "plan_review": review_payload}
            await user_gate.open_gate(
                item["call_id"],
                session_id=parent_session_id,
                kind="plan_review",
                meta=review_payload,
            )
            decision = await user_gate.await_gate(item["call_id"], timeout=900.0)
            action = str((decision or {}).get("action") or "deny").lower()
            feedback = str((decision or {}).get("feedback") or (decision or {}).get("reason") or "").strip()

            if action in ("approve", "allow", "accept"):
                # Leave plan mode for subsequent rounds in this turn
                agent_mode = "agent"
                meta0["agent_mode"] = "agent"
                # Refresh system prompt so PLAN MODE section is gone
                try:
                    from src.core_kernel.agent_prompts import build_system_prompt

                    new_sys = build_system_prompt(metadata=meta0)
                    for i, m in enumerate(working):
                        if m.role == ChatRole.SYSTEM:
                            working[i] = ChatMessage(role=ChatRole.SYSTEM, content=new_sys)
                            break
                except Exception:
                    pass
                yield {
                    "delta": "",
                    "done": False,
                    "plan_mode": {"active": False, "reason": "approved"},
                }
                payload = {
                    "id": item["call_id"],
                    "name": item["name"],
                    "plugin_id": "builtin.workspace",
                    "success": True,
                    "result": {
                        "approved": True,
                        "message": (
                            "Plan approved — plan mode exited; carry out the plan "
                            "starting with your next step."
                        ),
                    },
                    "error": None,
                    "duration_ms": 0,
                    "kind": "plan_review",
                }
            elif action == "deny" and not feedback:
                # User dismissed to speak instead
                payload = {
                    "id": item["call_id"],
                    "name": item["name"],
                    "plugin_id": "builtin.workspace",
                    "success": False,
                    "result": None,
                    "error": (
                        "The user dismissed the plan review to speak instead; "
                        "stay in plan mode, stop here, and wait for their message."
                    ),
                    "duration_ms": 0,
                    "kind": "plan_review",
                }
            else:
                # Keep planning
                err = (
                    f"The user chose to keep planning; their feedback: {feedback}"
                    if feedback
                    else "The user chose to keep planning; revise the plan and present it again."
                )
                payload = {
                    "id": item["call_id"],
                    "name": item["name"],
                    "plugin_id": "builtin.workspace",
                    "success": False,
                    "result": None,
                    "error": err,
                    "duration_ms": 0,
                    "kind": "plan_review",
                }
            yield {"delta": "", "done": False, "tool_result": payload}
            _append_tool_result(payload)

        for item in stream_items:
            async for ev in _execute_subagent_tool(
                gateway=gateway,
                plugins=plugins,
                item=item,
                provider=provider,
                model=model,
                task_id=task_id,
                workspace_cwd=workspace_cwd,
                workspace_meta=workspace_meta or {},
                parent_session_id=parent_session_id,
                parent_depth=depth,
                parent_messages=working[:-1],
            ):
                if ev.get("tool_result"):
                    payload = ev["tool_result"]
                    yield {"delta": "", "done": False, "tool_result": payload}
                    _append_tool_result({**payload, "kind": "subagent"})
                else:
                    yield ev

    # budget exceeded
    from src.core_kernel.context_compact import compact_messages

    final_msgs = compact_messages(
        working
        + [
            ChatMessage(
                role=ChatRole.USER,
                content=(
                    "Tool loop budget reached. Summarize what you already changed or found, "
                    "and list remaining steps. Do not call more tools unless a single critical read is required."
                ),
            )
        ],
        model_name=model,
    )
    from src.core_kernel.tool_history import sanitize_tool_call_messages

    req = ModelRequest(
        provider=provider,
        model=model,
        messages=sanitize_tool_call_messages(final_msgs),
        tools=openai_tools or None,
        stream=True,
        reasoning_effort=reasoning_effort,
    )
    emit_extension_event(
        "model_request",
        {
            "session_id": parent_session_id,
            "provider": provider,
            "model": model,
            "round": "budget",
            "tool_count": len(openai_tools or []),
        },
    )
    collected = ""
    async for chunk in gateway.stream(req, task_id=task_id):
        if getattr(chunk, "reasoning", None):
            yield {"delta": "", "done": False, "reasoning_delta": chunk.reasoning}
        if chunk.content:
            collected += chunk.content
            yield {"delta": chunk.content, "done": False}
        if chunk.usage:
            usage_total = _add_usage(usage_total, _extract_usage(chunk.usage))
    emit_extension_event(
        "model_response",
        {
            "session_id": parent_session_id,
            "round": "budget",
            "content_len": len(collected or ""),
            "had_tool_calls": False,
        },
    )
    yield _finish_turn(
        {
            "delta": "",
            "done": True,
            "content": collected or last_collected,
            "usage": _stamp_usage(),
            "error": "tool loop exceeded max rounds",
        }
    )


async def _execute_subagent_tool(
    *,
    gateway: ModelGateway,
    plugins: PluginManager,
    item: Dict[str, Any],
    provider: Optional[str],
    model: Optional[str],
    task_id: Optional[str],
    workspace_cwd: Optional[str],
    workspace_meta: Dict[str, Any],
    parent_session_id: str,
    parent_depth: int,
    parent_messages: List[ChatMessage],
) -> AsyncIterator[Dict[str, Any]]:
    from src.core_kernel.subagent.registry import get_subagent_registry
    from src.core_kernel.subagent.runner import MAX_SUBAGENT_DEPTH, run_subagent_turn

    base = item["base"]
    args = item["args"]
    call_id = item["call_id"]
    name = item["name"]
    registry = get_subagent_registry()
    started = time.perf_counter()

    if base == "send_message":
        agent_id = str(args.get("agent_id") or "").strip()
        message = str(args.get("message") or "").strip()
        if not agent_id or not message:
            yield {
                "tool_result": {
                    "id": call_id,
                    "name": name,
                    "plugin_id": "builtin.subagent",
                    "success": False,
                    "result": None,
                    "error": "agent_id and message required",
                    "duration_ms": 0,
                    "kind": "subagent",
                }
            }
            return
        rec = await registry.hydrate(agent_id)
        if not rec:
            yield {
                "tool_result": {
                    "id": call_id,
                    "name": name,
                    "plugin_id": "builtin.subagent",
                    "success": False,
                    "result": None,
                    "error": f"subagent not found: {agent_id}",
                    "duration_ms": 0,
                    "kind": "subagent",
                }
            }
            return
        # Rebind call for UI card streaming
        rec.parent_call_id = call_id
        final_output = ""
        error = None
        async for ev in run_subagent_turn(
            gateway=gateway,
            plugins=plugins,
            record=rec,
            user_prompt=message,
            parent_call_id=call_id,
            task_id=task_id,
        ):
            if ev.get("subagent"):
                yield ev
                if ev["subagent"].get("phase") == "end":
                    final_output = ev["subagent"].get("output") or ""
                    error = ev["subagent"].get("error")
        yield {
            "tool_result": {
                "id": call_id,
                "name": name,
                "plugin_id": "builtin.subagent",
                "success": not error,
                "result": {
                    "kind": "message",
                    "subagent_id": agent_id,
                    "messageId": f"msg_{call_id[-8:]}",
                    "output": final_output,
                    "render": f"message delivered to agent {agent_id}",
                },
                "error": error,
                "duration_ms": (time.perf_counter() - started) * 1000,
                "kind": "subagent",
            }
        }
        return

    # spawn / fork
    if parent_depth >= MAX_SUBAGENT_DEPTH:
        yield {
            "tool_result": {
                "id": call_id,
                "name": name,
                "plugin_id": "builtin.subagent",
                "success": False,
                "result": None,
                "error": f"max subagent depth {MAX_SUBAGENT_DEPTH} reached",
                "duration_ms": 0,
                "kind": "subagent",
            }
        }
        return

    label = str(args.get("description") or args.get("label") or "subagent").strip()
    prompt = str(args.get("prompt") or "").strip()
    if not prompt:
        yield {
            "tool_result": {
                "id": call_id,
                "name": name,
                "plugin_id": "builtin.subagent",
                "success": False,
                "result": None,
                "error": "prompt required",
                "duration_ms": 0,
                "kind": "subagent",
            }
        }
        return

    mode = "fork" if base == "subagent_fork" else "spawn"
    seed: List[ChatMessage] = []
    if mode == "fork":
        # Inherit completed conversation; skip system (child gets its own) and skip empty assistant stubs
        for m in parent_messages:
            if m.role == ChatRole.SYSTEM:
                continue
            seed.append(m)

    rec = registry.create(
        label=label,
        mode=mode,
        parent_session_id=parent_session_id or str(workspace_meta.get("session_id") or ""),
        parent_task_id=task_id or "",
        parent_call_id=call_id,
        depth=parent_depth + 1,
        provider=provider,
        model=model,
        workspace_cwd=workspace_cwd,
        workspace_meta=workspace_meta,
        seed_messages=seed,
    )
    try:
        await registry.persist(rec)
    except Exception:
        pass

    final_output = ""
    error = None
    status = "idle"
    async for ev in run_subagent_turn(
        gateway=gateway,
        plugins=plugins,
        record=rec,
        user_prompt=prompt,
        parent_call_id=call_id,
        task_id=task_id,
    ):
        if ev.get("subagent"):
            yield ev
            if ev["subagent"].get("phase") == "end":
                final_output = ev["subagent"].get("output") or ""
                error = ev["subagent"].get("error")
                status = ev["subagent"].get("status") or status

    yield {
        "tool_result": {
            "id": call_id,
            "name": name,
            "plugin_id": "builtin.subagent",
            "success": not error,
            "result": {
                "kind": "foreground",
                "subagent_id": rec.id,
                "mode": mode,
                "label": label,
                "status": status,
                "output": final_output,
                "render": final_output or f"subagent {rec.id} finished",
            },
            "error": error,
            "duration_ms": (time.perf_counter() - started) * 1000,
            "kind": "subagent",
        }
    }
