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
APPROVAL_TOOLS = {"run_shell", "write_file", "edit_file"}
PLAN_ALLOWED_TOOLS = {"glob", "grep", "list_dir", "read_file", "ask_user"}


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
        return plugin_id, tool_name
    for pid, tools in ((p.plugin_id, p.manifest.tools) for p in plugins.plugins.values()):
        for t in tools:
            if t.get("name") == name:
                return pid, name
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
    if "_" in n and n not in (
        SUBAGENT_ALL | APPROVAL_TOOLS | PLAN_ALLOWED_TOOLS | {ASK_USER_TOOL}
    ):
        # builtin.workspace_run_shell style uncommon; prefer last segment after plugin prefix
        pass
    return n


def _filter_openai_tools(
    tools: List[Dict[str, Any]],
    allow_subagents: bool,
    *,
    agent_mode: str = "agent",
) -> List[Dict[str, Any]]:
    out = []
    plan = agent_mode == "plan"
    for t in tools:
        name = ((t.get("function") or {}).get("name") or "")
        base = _base_tool_name(name)
        if not allow_subagents and base in SUBAGENT_ALL:
            continue
        if plan and base not in PLAN_ALLOWED_TOOLS:
            continue
        out.append(t)
    return out


def _base_tool_name(name: str) -> str:
    # Accept both short and prefixed forms
    raw = name or ""
    if raw in SUBAGENT_ALL or raw == ASK_USER_TOOL or raw in APPROVAL_TOOLS or raw in PLAN_ALLOWED_TOOLS:
        return raw
    for short in SUBAGENT_ALL | {ASK_USER_TOOL} | APPROVAL_TOOLS | PLAN_ALLOWED_TOOLS:
        if raw.endswith("_" + short) or raw.endswith("." + short) or raw == short:
            return short
    # strip plugin prefix "builtin.workspace_xxx" unlikely; try last token
    if "." in raw:
        return raw.rsplit(".", 1)[-1]
    return raw


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
    rounds = max_rounds
    if workspace_cwd:
        rounds = max(rounds, 20)
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
    auto_accept = bool(meta0.get("auto_accept"))
    openai_tools = (
        _filter_openai_tools(plugins.as_openai_tools(), allow_subagents, agent_mode=agent_mode)
        if tools_enabled
        else []
    )
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

    def _stamp_usage() -> Dict[str, Any]:
        out = dict(usage_total)
        out["duration_ms"] = (time.perf_counter() - turn_started) * 1000
        return out

    for round_i in range(max_rounds):
        if cancel_event and cancel_event.is_set():
            yield {
                "delta": "",
                "done": True,
                "content": last_collected,
                "usage": _stamp_usage(),
                "error": "interrupted",
                "cancelled": True,
            }
            return

        req = ModelRequest(
            provider=provider,
            model=model,
            messages=working,
            tools=openai_tools or None,
            stream=True,
        )
        collected = ""
        tool_acc: Dict[int, Dict[str, Any]] = {}
        round_usage: Dict[str, Any] = {}

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
            if chunk.tool_calls:
                _merge_tool_call_deltas(tool_acc, chunk.tool_calls)
            if chunk.usage:
                round_usage = _extract_usage(chunk.usage)

        if cancel_event and cancel_event.is_set():
            yield {
                "delta": "",
                "done": True,
                "content": collected or last_collected,
                "usage": _stamp_usage(),
                "error": "interrupted",
                "cancelled": True,
            }
            return

        last_collected = collected
        if round_usage.get("total_tokens"):
            usage_total = _add_usage(usage_total, round_usage)
        else:
            usage_total = _add_usage(usage_total, estimate_usage(working, collected))

        finalized = [tool_acc[i] for i in sorted(tool_acc.keys())] if tool_acc else []
        if not finalized:
            out = {
                "delta": "",
                "done": True,
                "content": collected,
                "usage": _stamp_usage(),
            }
            if agent_mode == "plan" and (collected or "").strip():
                out["plan_ready"] = True
            yield out
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
            yield {"delta": "", "done": False, "tool_call": tool_payload}
            pending.append({"call_id": call_id, "name": name, "base": base, "args": args})

        stream_items = [p for p in pending if p["base"] in SUBAGENT_STREAM_TOOLS]
        ask_items = [p for p in pending if p["base"] == ASK_USER_TOOL]
        other_items = [
            p for p in pending if p["base"] not in SUBAGENT_STREAM_TOOLS and p["base"] != ASK_USER_TOOL
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

            if agent_mode == "plan" and base not in PLAN_ALLOWED_TOOLS:
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

            plugin_id, tool_name = _resolve_plugin_tool(plugins, tool_map, name)
            if base in SUBAGENT_CONTROL_TOOLS:
                args["_parent_session_id"] = parent_session_id
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
            timeout = 60.0
            if base == "run_shell":
                try:
                    timeout = float(args.get("timeout_seconds") or 60)
                except (TypeError, ValueError):
                    timeout = 60.0
            result = await plugins.invoke(
                PluginInvokeRequest(
                    plugin_id=plugin_id,
                    tool_name=tool_name,
                    arguments=args,
                    timeout_seconds=timeout,
                ),
                task_id=task_id,
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
            p for p in other_items if auto_accept or p["base"] not in APPROVAL_TOOLS
        ]
        risky_items = [
            p for p in other_items if (not auto_accept) and p["base"] in APPROVAL_TOOLS
        ]

        if safe_items:
            payloads = await asyncio.gather(*[_invoke_tool(item) for item in safe_items])
            for payload in payloads:
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
            decision = await user_gate.await_gate(item["call_id"], timeout=600.0)
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
    req = ModelRequest(
        provider=provider,
        model=model,
        messages=working
        + [
            ChatMessage(
                role=ChatRole.USER,
                content=(
                    "Tool loop budget reached. Summarize what you already changed or found, "
                    "and list remaining steps. Do not call more tools unless a single critical read is required."
                ),
            )
        ],
        tools=openai_tools or None,
        stream=True,
    )
    collected = ""
    async for chunk in gateway.stream(req, task_id=task_id):
        if chunk.content:
            collected += chunk.content
            yield {"delta": chunk.content, "done": False}
        if chunk.usage:
            usage_total = _add_usage(usage_total, _extract_usage(chunk.usage))
    yield {
        "delta": "",
        "done": True,
        "content": collected or last_collected,
        "usage": _stamp_usage(),
        "error": "tool loop exceeded max rounds",
    }


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
        rec = registry.get(agent_id)
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
