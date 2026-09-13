# Workspaces — coding agent working directories

## Idea (DSH-inspired, NLM shape)

| Layer | Role |
|-------|------|
| **Workspace registry** | UI project list in `data/workspaces.json` (`id`, `path`, `title`, `session_ids`) |
| **Session `cwd`** | Bound once on the Redis session; tools resolve paths against it |
| **Tools** | `builtin.workspace` — `glob` / `grep` / `list_dir` / `read_file` / `write_file` / `edit_file` / `run_shell`; plus `builtin.subagent` — see [subagents.md](./subagents.md) |

Models never see workspace registry IDs as a separate product concept beyond the system prompt; they get **cwd** + workspace tools.

## UI

1. Empty chat hero → **Workspace picker** (本机 / 远程 SSH)
2. Sidebar **工作目录** → click to open a new session bound to that workspace
3. Topbar chip shows active cwd (`SSH ·` prefix for remote)
4. Composer **blocks send** until a cwd is bound (Wave E)

See also: [ssh-workspaces.md](./ssh-workspaces.md)

## API

```bash
GET    /api/workspaces
POST   /api/workspaces                 # { "path": "E:\\proj", "title": "optional" }
DELETE /api/workspaces/{id}
GET    /api/workspaces/browse?path=    # local directory browser

POST   /api/sessions                   # { session_id?, workspace_id? | cwd? }
PATCH  /api/sessions/{id}/workspace    # bind / replace on empty chats
```

Chat may also pass `workspace_id` / `cwd` on `POST /api/chat` so the first message stamps the session.

## Agent behavior

- System prompt includes active workspace path when `task.metadata.cwd` is set
- Tool invoke context carries cwd (`NLM_WORKSPACE_CWD` for CLI plugins too)
- Paths cannot escape the workspace root
- Tool loop allows up to **64** rounds when a workspace is bound (see `AGENT_MAX_ROUNDS_WORKSPACE`)
- **Parallel tools (Wave E):** non-approval tools in a round run concurrently up to
  `AGENT_MAX_PARALLEL_TOOL_CALLS` (default **8**, barrier within each batch).
  Tools that need ApprovalDock / Feishu cards run **exclusive** (one gate at a time).
  Ask-user / plan-review are also exclusive.
- **`run_code` (Wave F):** execute a short Python snippet with `cwd=workspace` (approval like shell).
  Not DSH PTC — no nested tool SDK inside the snippet.
- OpenAI tool names for workspace tools are short (`grep`, `glob`, …) so models behave like DSH coding agents
- NLM extras stay available: Feishu channels, MCP/CLI plugins, web_search, Trajectory + right dock

## Coding loop (expected)

1. `glob` / `grep` / `list_dir` — locate
2. `read_file` — inspect (offset/limit)
3. `edit_file` / `write_file` — change
4. `run_shell` — verify
5. (optional) `open_canvas` — open lasting diagrams/tables beside chat

## Workspace metadata under `.nlm/`

When a **local** cwd is bound, NLM may write session artifacts under the workspace (never escapes the root):

| Path | Writer | Purpose |
|------|--------|---------|
| `.nlm/deliveries/*.md` | Delivery publish / plan approve | Plan → diagrams → code-change audit |
| `.nlm/canvases/*` | `open_canvas` / Canvas **保存** / `POST …/canvas` | Side-pane documents (mermaid, echarts, markdown, …) |
| `.nlm/instructions.md` | (optional, user) | Injected with `AGENTS.md` / `CLAUDE.md` into the system prompt |

SSH workspaces: chat file cards still work; **disk writes under `.nlm/` are local-only** today (same constraint as Delivery).

See [canvas.md](./canvas.md), [interaction-modes.md](./interaction-modes.md), [ssh-workspaces.md](./ssh-workspaces.md).

## Enable tools

Ensure plugin `builtin.workspace` is enabled (loaded by default). Toggle in the right dock if disabled.
