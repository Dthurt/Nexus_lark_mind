"""Builtin subagent tools — DSH-inspired spawn/fork/control surface."""

from __future__ import annotations

from typing import Any, Dict, List

from src.common.errors import PluginError, ValidationAppError
from src.core_kernel.plugin_runtime.lifecycle import BasePlugin, PluginManifest
from src.core_kernel.subagent.registry import get_subagent_registry

TOOLS: List[Dict[str, Any]] = [
    {
        "name": "subagent",
        "description": (
            "YOU decide when to call this — do not wait for the user to request a subagent. "
            "Spawn a fresh child that does NOT see this conversation; put everything it needs in `prompt`. "
            "Use for self-contained multi-step work you want isolated or run as a focused pass "
            "(research a subsystem, implement a bounded change, run a verify loop) while you orchestrate. "
            "Skip for trivial single grep/read/edit. Streams progress to the UI."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "Short 3–5 word label for the UI",
                },
                "prompt": {
                    "type": "string",
                    "description": "Complete standalone instructions for the child",
                },
                "run_in_background": {
                    "type": "boolean",
                    "description": "If true, mark continuable after finish (still streams this turn)",
                    "default": False,
                },
            },
            "required": ["description", "prompt"],
        },
    },
    {
        "name": "subagent_fork",
        "description": (
            "YOU decide when to call this. Fork a child that inherits completed turns from this conversation "
            "(not the current in-flight tool round). Use when the child needs prior context but a separate focus. "
            "Prompt should state only what is new. Prefer over `subagent` when context reuse matters; "
            "prefer `subagent` when isolation is better."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "description": {"type": "string", "description": "Short label"},
                "prompt": {"type": "string", "description": "What is new for the forked child"},
            },
            "required": ["description", "prompt"],
        },
    },
    {
        "name": "send_message",
        "description": (
            "Send a follow-up to a continuable/idle child from `list_agents` when YOU need to steer or continue it. "
            "Does not return the child's reply in this tool result — watch the subagent card stream."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string"},
                "message": {"type": "string"},
            },
            "required": ["agent_id", "message"],
        },
    },
    {
        "name": "interrupt_agent",
        "description": "Interrupt a running subagent's current turn when YOU decide it should stop.",
        "inputSchema": {
            "type": "object",
            "properties": {"agent_id": {"type": "string"}},
            "required": ["agent_id"],
        },
    },
    {
        "name": "list_agents",
        "description": "List this session's subagents when YOU need to manage or continue them.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "scope": {
                    "type": "string",
                    "enum": ["children", "descendants"],
                    "default": "children",
                }
            },
        },
    },
]


TEAM_TOOLS: List[Dict[str, Any]] = [
    {
        "name": "team_send",
        "description": (
            "EXPERIMENTAL (NLM_EXPERIMENTAL_TEAMS): post a message to the in-process team mailbox "
            "for another agent id (or '*' broadcast). Not durable across restarts."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "team_id": {"type": "string", "description": "Team / session scope id"},
                "to_id": {"type": "string", "description": "Target agent id or *"},
                "payload": {"type": "object"},
                "from_id": {"type": "string", "description": "Optional sender id"},
            },
            "required": ["team_id", "to_id"],
        },
    },
    {
        "name": "team_recv",
        "description": (
            "EXPERIMENTAL: claim pending team mailbox messages addressed to this agent (or *)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "team_id": {"type": "string"},
                "agent_id": {"type": "string"},
                "max_n": {"type": "integer", "default": 8},
            },
            "required": ["team_id", "agent_id"],
        },
    },
]


class SubagentToolsPlugin(BasePlugin):
    """Schemas only for control tools; spawn/fork streaming is handled in agent_runner."""

    async def _on_init(self) -> None:
        return None

    async def _on_ready(self) -> None:
        from src.common.config import get_settings

        tools = list(TOOLS)
        if get_settings().nlm_experimental_teams:
            tools.extend(TEAM_TOOLS)
        self.manifest.tools = tools

    async def _on_invoke(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        registry = get_subagent_registry()
        if tool_name == "list_agents":
            # parent_session_id injected by runner into arguments when available
            session_id = str(arguments.get("_parent_session_id") or "").strip()
            scope = str(arguments.get("scope") or "children")
            agents = (
                await registry.list_for_session_async(session_id, descendants=scope == "descendants")
                if session_id
                else []
            )
            return {
                "agents": [a.public() for a in agents],
                "count": len(agents),
                "render": "\n".join(
                    f"{a.id} [{a.status}] depth={a.depth} — {a.label}" for a in agents
                )
                or "(no subagents)",
            }
        if tool_name == "interrupt_agent":
            agent_id = str(arguments.get("agent_id") or "").strip()
            if not agent_id:
                raise ValidationAppError("agent_id required")
            rec = await registry.hydrate(agent_id)
            ok = registry.interrupt(agent_id) if rec else False
            if rec:
                try:
                    await registry.persist(rec)
                except Exception:
                    pass
            if not ok:
                raise ValidationAppError(f"subagent not found: {agent_id}")
            return {"accepted": True, "agent_id": agent_id, "render": f"interrupt requested for agent {agent_id}"}
        if tool_name == "team_send":
            from src.common.config import get_settings
            from src.core_kernel.teams import get_team_mailbox

            if not get_settings().nlm_experimental_teams:
                raise ValidationAppError("team_send requires NLM_EXPERIMENTAL_TEAMS=true")
            team_id = str(arguments.get("team_id") or "").strip()
            to_id = str(arguments.get("to_id") or "*").strip() or "*"
            from_id = str(arguments.get("from_id") or arguments.get("_parent_session_id") or "parent").strip()
            payload = arguments.get("payload") if isinstance(arguments.get("payload"), dict) else {}
            if not team_id:
                raise ValidationAppError("team_id required")
            msg = get_team_mailbox().post(team_id, from_id=from_id, to_id=to_id, payload=payload)
            return {
                "ok": True,
                "message_id": msg.id,
                "render": f"posted {msg.id} → {to_id}",
            }
        if tool_name == "team_recv":
            from src.common.config import get_settings
            from src.core_kernel.teams import get_team_mailbox

            if not get_settings().nlm_experimental_teams:
                raise ValidationAppError("team_recv requires NLM_EXPERIMENTAL_TEAMS=true")
            team_id = str(arguments.get("team_id") or "").strip()
            agent_id = str(arguments.get("agent_id") or "").strip()
            max_n = int(arguments.get("max_n") or 8)
            if not team_id or not agent_id:
                raise ValidationAppError("team_id and agent_id required")
            msgs = get_team_mailbox().claim(team_id, agent_id, max_n=max_n)
            return {
                "ok": True,
                "count": len(msgs),
                "messages": [
                    {
                        "id": m.id,
                        "from_id": m.from_id,
                        "to_id": m.to_id,
                        "payload": m.payload,
                        "created_at": m.created_at,
                    }
                    for m in msgs
                ],
                "render": f"claimed {len(msgs)} message(s)",
            }
        if tool_name in {"subagent", "subagent_fork", "send_message"}:
            # Streaming path should intercept before invoke; fallback message:
            raise PluginError(
                f"{tool_name} must be executed by the agent runner streaming path"
            )
        raise PluginError(f"unknown subagent tool: {tool_name}")

    async def _on_teardown(self) -> None:
        return None


def subagent_tools_manifest() -> PluginManifest:
    from src.common.config import get_settings

    tools = list(TOOLS)
    try:
        if get_settings().nlm_experimental_teams:
            tools.extend(TEAM_TOOLS)
    except Exception:
        pass
    return PluginManifest(
        plugin_id="builtin.subagent",
        name="Subagent",
        kind="inprocess",
        version="1.1.0",
        description="Delegate work to spawn/fork subagents with streaming UI (DSH-inspired).",
        tools=tools,
    )
