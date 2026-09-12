# Multi-backend subagents & ACP bridge

## Today

| Backend | Status |
|---------|--------|
| **inprocess** | Default — `SubagentRegistry` + nested agent loop |
| Codex / Claude Code CLI | Not shipped |
| Full ACP server | Not shipped |

Protocol: `src/core_kernel/subagent/backend.py` (`SubagentBackend` + `InProcessBackend`).

```text
GET  /api/acp/backends
POST /api/acp/backends/{backend}/spawn   { session_id, prompt, cwd?, model? }
POST /api/acp/sessions                  → create workbench session
POST /api/acp/sessions/{id}/prompt      → enqueue /api/chat
GET  /api/chat/stream?session_id=…      → existing SSE (ACP clients subscribe here)
```

Nexus remains an **HTTP + SSE** coding workbench. The ACP routes are a thin bridge onto chat + in-process subagents — not a conforming ACP host.

## Future sketch

```text
SubagentBackend
  - spawn(prompt, cwd, model?) -> handle
  - describe(handle) / stream events compatible with task.subagent SSE
```

Candidate backends (not shipped): ACP thin adapter host process; Codex/Claude Code CLI adapters.
