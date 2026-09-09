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


class SubagentToolsPlugin(BasePlugin):
    """Schemas only for control tools; spawn/fork streaming is handled in agent_runner."""

    async def _on_init(self) -> None:
        return None

    async def _on_ready(self) -> None:
        self.manifest.tools = list(TOOLS)

    async def _on_invoke(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        registry = get_subagent_registry()
        if tool_name == "list_agents":
            # parent_session_id injected by runner into arguments when available
            session_id = str(arguments.get("_parent_session_id") or "").strip()
            scope = str(arguments.get("scope") or "children")
            agents = registry.list_for_session(session_id, descendants=scope == "descendants") if session_id else []
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
            ok = registry.interrupt(agent_id)
            if not ok:
                raise ValidationAppError(f"subagent not found: {agent_id}")
            return {"accepted": True, "agent_id": agent_id, "render": f"interrupt requested for agent {agent_id}"}
        if tool_name in {"subagent", "subagent_fork", "send_message"}:
            # Streaming path should intercept before invoke; fallback message:
            raise PluginError(
                f"{tool_name} must be executed by the agent runner streaming path"
            )
        raise PluginError(f"unknown subagent tool: {tool_name}")

    async def _on_teardown(self) -> None:
        return None


def subagent_tools_manifest() -> PluginManifest:
    return PluginManifest(
        plugin_id="builtin.subagent",
        name="Subagent",
        kind="inprocess",
        version="1.0.0",
        description="Delegate work to spawn/fork subagents with streaming UI (DSH-inspired).",
        tools=list(TOOLS),
    )
