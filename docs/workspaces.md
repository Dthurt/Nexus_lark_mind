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
- Tool loop allows up to **20** rounds when a workspace is bound (parallel tool calls in a round)
- OpenAI tool names for workspace tools are short (`grep`, `glob`, …) so models behave like DSH coding agents
- NLM extras stay available: Feishu channels, MCP/CLI plugins, web_search, Trajectory + right dock

## Coding loop (expected)

1. `glob` / `grep` / `list_dir` — locate
2. `read_file` — inspect (offset/limit)
3. `edit_file` / `write_file` — change
4. `run_shell` — verify

## Enable tools

Ensure plugin `builtin.workspace` is enabled (loaded by default). Toggle in the right dock if disabled.
