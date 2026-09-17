"""Sample extension — logs tool calls and can tighten active tools.

Drop custom modules under `.nlm/extensions/` or `plugins_volume/extensions/`.
Each file must define `register(api)`.
"""


def register(api):
    def on_tool_call(ctx):
        # Example spawn-hook: inject CI=true for shell (non-blocking)
        base = str(ctx.get("base") or "")
        if base == "run_shell":
            args = dict(ctx.get("arguments") or {})
            env = dict(args.get("env") or {})
            env.setdefault("NLM_EXTENSION", "sample_logger")
            return {"arguments": {**args, "env": env}}
        return None

    def on_before_start(ctx):
        # No-op marker for tests / observability
        return {"ok": True, "extension": "sample_logger"}

    api.on("tool_call", on_tool_call)
    api.on("before_agent_start", on_before_start)
    api.register_command(
        "tools-readonly",
        {
            "description": "Converge active tools to read-only subset",
            "handler": "set_active_tools:read_file,grep,glob,list_dir,kb_search,kb_read",
        },
    )
