"""Unified Extension event system (Pi-inspired).

Discover Python modules under:
  <cwd>/.nlm/extensions/*.py
  plugins_volume/extensions/*.py

Each module may define:

  def register(api: ExtensionAPI) -> None:
      api.on("tool_call", handler)
      api.register_tool(...)
      api.register_command(...)

Lifecycle events (emitted by agent runner / SessionContext / hooks):
  session_start, session_end, before_agent_start, after_agent_turn,
  tool_call, tool_result, model_request, model_response,
  user_message, compaction

Dynamic tools:
  api.get_active_tools() / api.set_active_tools(names)
"""

from __future__ import annotations

import importlib.util
import inspect
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

EventHandler = Callable[[Dict[str, Any]], Any]
ToolDef = Dict[str, Any]
CommandDef = Dict[str, Any]

KNOWN_EVENTS = frozenset(
    {
        "session_start",
        "session_end",
        "before_agent_start",
        "after_agent_turn",
        "tool_call",
        "tool_result",
        "model_request",
        "model_response",
        "user_message",
        "user_bash",
        "compaction",
        "pre_compact",
        "post_compact",
        "session_persist",
        "extension",  # inter-extension bus
    }
)


@dataclass
class ExtensionAPI:
    """API handed to each extension's register(api) entrypoint."""

    name: str
    _bus: "EventBus"
    _registry: "ExtensionRegistry"

    def on(self, event: str, handler: EventHandler) -> None:
        self._bus.on(event, handler, source=self.name)

    def emit(self, event: str, payload: Optional[Dict[str, Any]] = None) -> List[Any]:
        data = dict(payload or {})
        data.setdefault("_from", self.name)
        return self._bus.emit(event, data)

    def register_tool(self, definition: ToolDef) -> None:
        self._registry.register_tool(self.name, definition)

    def register_command(self, name: str, options: Optional[Dict[str, Any]] = None) -> None:
        self._registry.register_command(self.name, name, options or {})

    def register_flag(self, name: str, options: Optional[Dict[str, Any]] = None) -> None:
        self._registry.register_flag(self.name, name, options or {})

    def get_flag(self, name: str) -> Any:
        """Read a registered flag (env NLM_FLAG_<NAME> or options.env)."""
        return self._registry.get_flag(name)

    def get_active_tools(self) -> Optional[List[str]]:
        return self._registry.get_active_tools()

    def set_active_tools(self, names: Optional[List[str]]) -> None:
        self._registry.set_active_tools(names)

    @property
    def events(self) -> "EventBus":
        return self._bus


class EventBus:
    def __init__(self) -> None:
        self._handlers: Dict[str, List[tuple[str, EventHandler]]] = {}
        self._lock = threading.RLock()

    def on(self, event: str, handler: EventHandler, *, source: str = "") -> None:
        key = (event or "").strip()
        if not key or not callable(handler):
            return
        with self._lock:
            self._handlers.setdefault(key, []).append((source, handler))

    def off(self, event: str, handler: Optional[EventHandler] = None) -> None:
        key = (event or "").strip()
        with self._lock:
            if key not in self._handlers:
                return
            if handler is None:
                self._handlers.pop(key, None)
                return
            self._handlers[key] = [(s, h) for s, h in self._handlers[key] if h is not handler]

    def emit(self, event: str, payload: Optional[Dict[str, Any]] = None) -> List[Any]:
        key = (event or "").strip()
        data = dict(payload or {})
        data.setdefault("event", key)
        with self._lock:
            handlers = list(self._handlers.get(key, []))
            # Also fan-out to wildcard listeners
            handlers.extend(self._handlers.get("*", []))
        results: List[Any] = []
        for source, handler in handlers:
            try:
                results.append(handler(data))
            except Exception as exc:
                logger.warning("extension handler error (%s/%s): %s", source, key, exc)
                results.append({"error": str(exc), "source": source})
        return results

    def clear(self) -> None:
        with self._lock:
            self._handlers.clear()


@dataclass
class ExtensionRegistry:
    bus: EventBus = field(default_factory=EventBus)
    tools: Dict[str, ToolDef] = field(default_factory=dict)
    commands: Dict[str, CommandDef] = field(default_factory=dict)
    flags: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    loaded: List[str] = field(default_factory=list)
    _active_tools: Optional[Set[str]] = None
    _lock: threading.RLock = field(default_factory=threading.RLock)

    def register_tool(self, ext_name: str, definition: ToolDef) -> None:
        name = str(definition.get("name") or "").strip()
        if not name:
            return
        with self._lock:
            self.tools[name] = {**definition, "_extension": ext_name}

    def register_command(self, ext_name: str, name: str, options: Dict[str, Any]) -> None:
        key = (name or "").strip().lstrip("/")
        if not key:
            return
        with self._lock:
            self.commands[key] = {**options, "name": key, "_extension": ext_name}

    def register_flag(self, ext_name: str, name: str, options: Dict[str, Any]) -> None:
        key = (name or "").strip()
        if not key:
            return
        with self._lock:
            self.flags[key] = {**options, "name": key, "_extension": ext_name}

    def get_flag(self, name: str) -> Any:
        spec = self.flags.get((name or "").strip())
        if not spec:
            return None
        env_key = str(spec.get("env") or f"NLM_FLAG_{name.upper().replace('-', '_')}")
        raw = (os.getenv(env_key) or "").strip()
        typ = str(spec.get("type") or "boolean")
        if raw == "":
            return spec.get("default")
        if typ == "boolean":
            return raw.lower() in {"1", "true", "yes", "on"}
        return raw

    def public_flags(self) -> List[Dict[str, Any]]:
        with self._lock:
            items = list(self.flags.values())
        out: List[Dict[str, Any]] = []
        for spec in items:
            name = str(spec.get("name") or "")
            out.append(
                {
                    "name": name,
                    "type": spec.get("type") or "boolean",
                    "description": spec.get("description") or "",
                    "env": spec.get("env") or f"NLM_FLAG_{name.upper().replace('-', '_')}",
                    "default": spec.get("default"),
                    "value": self.get_flag(name),
                    "extension": spec.get("_extension") or "",
                }
            )
        return out

    def get_active_tools(self) -> Optional[List[str]]:
        with self._lock:
            if self._active_tools is None:
                return None
            return sorted(self._active_tools)

    def set_active_tools(self, names: Optional[List[str]]) -> None:
        with self._lock:
            if names is None:
                self._active_tools = None
            else:
                self._active_tools = {str(n).strip() for n in names if str(n).strip()}

    def filter_openai_tools(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Apply active-tool subset if set. Names match function.name or leaf."""
        with self._lock:
            active = self._active_tools
        if not active:
            return tools
        out: List[Dict[str, Any]] = []
        for t in tools:
            fn = (t.get("function") or {}) if isinstance(t, dict) else {}
            name = str(fn.get("name") or "")
            leaf = name.rsplit(".", 1)[-1] if name else ""
            # Always keep ask_user / exit_plan_mode for control flow
            if name in active or leaf in active:
                out.append(t)
                continue
            if leaf in {"ask_user", "exit_plan_mode", "todo_write"}:
                out.append(t)
        return out

    def as_openai_extension_tools(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        with self._lock:
            items = list(self.tools.items())
        for name, tool in items:
            params = tool.get("inputSchema") or tool.get("parameters") or {
                "type": "object",
                "properties": {},
            }
            out.append(
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": tool.get("description") or f"Extension tool {name}",
                        "parameters": params,
                    },
                }
            )
        return out

    def reset(self) -> None:
        with self._lock:
            self.tools.clear()
            self.commands.clear()
            self.flags.clear()
            self.loaded.clear()
            self._active_tools = None
        self.bus.clear()


_GLOBAL = ExtensionRegistry()


def get_extension_registry() -> ExtensionRegistry:
    return _GLOBAL


def _extension_dirs(cwd: Optional[str] = None) -> List[Path]:
    paths: List[Path] = []
    if cwd:
        paths.append(Path(cwd) / ".nlm" / "extensions")
    paths.append(Path("plugins_volume") / "extensions")
    root = Path(__file__).resolve().parents[2]
    paths.append(root / "plugins_volume" / "extensions")
    return paths


def _load_module(path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(f"nlm_ext_{path.stem}", path)
    if not spec or not spec.loader:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def discover_and_load_extensions(
    cwd: Optional[str] = None,
    *,
    registry: Optional[ExtensionRegistry] = None,
    reload: bool = False,
) -> ExtensionRegistry:
    """Scan extension dirs and call register(api) on each module."""
    reg = registry or get_extension_registry()
    if reload:
        reg.reset()
    seen: Set[str] = set()
    for directory in _extension_dirs(cwd):
        if not directory.is_dir():
            continue
        try:
            files = sorted(directory.glob("*.py"))
        except OSError:
            continue
        for path in files:
            if path.name.startswith("_"):
                continue
            key = path.stem
            if key in seen:
                continue
            seen.add(key)
            try:
                mod = _load_module(path)
            except Exception as exc:
                logger.warning("extension load failed (%s): %s", path, exc)
                continue
            if mod is None:
                continue
            register = getattr(mod, "register", None)
            if not callable(register):
                logger.debug("extension %s has no register()", path)
                continue
            api = ExtensionAPI(name=key, _bus=reg.bus, _registry=reg)
            try:
                register(api)
                reg.loaded.append(str(path))
            except Exception as exc:
                logger.warning("extension register failed (%s): %s", path, exc)
    return reg


def emit_extension_event(event: str, payload: Optional[Dict[str, Any]] = None) -> List[Any]:
    return get_extension_registry().bus.emit(event, payload)


def lookup_extension_tool(name: str) -> Optional[ToolDef]:
    """Resolve a tool registered via api.register_tool (short name or leaf)."""
    key = (name or "").strip()
    if not key:
        return None
    tools = get_extension_registry().tools
    if key in tools:
        return tools[key]
    leaf = key.rsplit(".", 1)[-1]
    return tools.get(leaf)


async def invoke_extension_tool(name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Run an extension-registered tool handler. Returns a plugin-like envelope."""
    tool = lookup_extension_tool(name)
    if not tool:
        return {"ok": False, "error": f"unknown extension tool: {name}"}
    handler = tool.get("handler")
    if not callable(handler):
        return {
            "ok": False,
            "error": f"extension tool `{name}` has no callable handler",
        }
    t0 = time.perf_counter()
    try:
        result = handler(dict(arguments or {}))
        if inspect.isawaitable(result):
            result = await result
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc),
            "duration_ms": (time.perf_counter() - t0) * 1000,
        }
    duration_ms = (time.perf_counter() - t0) * 1000
    if isinstance(result, dict):
        out = dict(result)
        out.setdefault("ok", True)
        out["duration_ms"] = duration_ms
        return out
    return {"ok": True, "result": result, "duration_ms": duration_ms}


def apply_extension_slash_command(text: str) -> Optional[Dict[str, str]]:
    """Dispatch `/name` to an extension-registered command.

    Built-in handler protocol: ``set_active_tools:a,b,c`` converges the
    tool subset for the next agent turn. A ``prompt`` option (or callable
    handler returning text) becomes the expanded user message.
    """
    raw = (text or "").strip()
    if not raw.startswith("/"):
        return None
    parts = raw.split(None, 1)
    cmd = parts[0][1:].strip()
    rest = parts[1] if len(parts) > 1 else ""
    if not cmd:
        return None
    spec = get_extension_registry().commands.get(cmd)
    if not spec:
        return None
    handler = spec.get("handler")
    prompt = str(spec.get("prompt") or "").strip()
    if isinstance(handler, str) and handler.startswith("set_active_tools:"):
        names = [x.strip() for x in handler.split(":", 1)[1].split(",") if x.strip()]
        get_extension_registry().set_active_tools(names)
        if not prompt:
            prompt = (
                f"Active tools are now limited to: {', '.join(names)}. "
                + (rest.strip() or "Proceed with the user's next request using only these tools.")
            )
    elif callable(handler):
        try:
            extra = handler({"command": cmd, "rest": rest, "original": raw})
            if inspect.isawaitable(extra):
                extra = None  # slash expand is sync; ignore async handlers
            if isinstance(extra, dict):
                if extra.get("prompt"):
                    prompt = str(extra["prompt"])
                if extra.get("active_tools") is not None:
                    get_extension_registry().set_active_tools(
                        extra["active_tools"] if extra["active_tools"] else None
                    )
            elif extra:
                prompt = str(extra)
        except Exception as exc:
            logger.warning("extension slash handler failed (%s): %s", cmd, exc)
            return None
    if not prompt:
        return None
    return {
        "name": cmd,
        "prompt": prompt,
        "original": raw,
        "description": str(spec.get("description") or cmd),
    }


def run_tool_call_hooks(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """Emit tool_call; handlers may return block/arguments like pre_tool."""
    results = emit_extension_event("tool_call", ctx)
    merged: Dict[str, Any] = {"block": False}
    for r in results:
        if not isinstance(r, dict):
            continue
        if r.get("block"):
            merged["block"] = True
            if r.get("reason"):
                merged["reason"] = str(r["reason"])
        if isinstance(r.get("arguments"), dict):
            merged["arguments"] = r["arguments"]
        # Spawn-hook style transforms for shell
        for key in ("command", "cwd", "env"):
            if key in r and r[key] is not None:
                merged[key] = r[key]
    return merged
