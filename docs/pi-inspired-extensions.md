# Skills / Fork / Hooks / Extensions / Presets / Prompts

Nexus Lark Mind borrows **extension patterns** from Pi-style agent harnesses
without adopting Pi's "minimal core" product philosophy.

## Skills (progressive disclosure)

Place playbooks under the workspace:

```
.nlm/skills/<name>/SKILL.md
.agents/skills/<name>/SKILL.md
```

Optional YAML front matter:

```markdown
---
name: verify-change
description: Run focused checks after edits
allowed-tools: read_file, grep, glob, list_dir, run_shell
---
# body …
```

- System prompt lists **name + description + path** only.
- Model should `read_file` the skill path when relevant.
- User / Command Palette can insert `/skill:<name> …`.
- When `/skill:name` is used and `allowed-tools` is set, the agent **converges**
  the OpenAI tool list to that subset for the turn (Dynamic Tool Loading).
- API: `GET /api/skills?cwd=<path>`

Example skill ships at `.nlm/skills/verify-change/SKILL.md` (repo root).

## Unified Extension event system

Python modules under:

```
<cwd>/.nlm/extensions/*.py
plugins_volume/extensions/*.py
```

```python
def register(api):
    api.on("tool_call", handler)           # may return block / arguments / command / cwd / env
    api.on("before_agent_start", handler)
    api.register_tool({...})
    api.register_command("name", {...})
    api.set_active_tools(["read_file", "grep"])
```

Events: `session_start`, `before_agent_start`, `after_agent_turn`, `tool_call`,
`tool_result`, `model_request`, `model_response`, `user_message`, `compaction`, …

Sample: `plugins_volume/extensions/sample_logger.py`.

Pre-tool hooks (below) still run; extension `tool_call` handlers run afterward
and can transform shell spawn fields (`command` / `cwd` / `env`).

## Dynamic Tool Loading

Priority for the active tool subset:

1. Session `active_tools` (set via interaction patch or preset)
2. Skill `allowed-tools` when user invokes `/skill:…`
3. Extension registry `api.set_active_tools(...)`

Control tools (`ask_user`, `exit_plan_mode`, `todo_write`) are always kept.

```http
PATCH /api/sessions/{id}/interaction
{ "active_tools": ["read_file", "grep"], "preset_name": "code-review" }
```

## Session fork + tree navigation

```http
POST /api/sessions/{id}/fork
{ "until_index": 12, "title": "Try plan B" }
```

Child sessions store `parent_id`, `forked_from`, and `fork_point_index`.

```http
GET /api/sessions/tree?workspace_id=
POST /api/sessions/{id}/bookmarks   { "message_index": 5, "label": "decision" }
DELETE /api/sessions/{id}/bookmarks/{message_index}
```

Web: Command Palette → **从此会话分叉** / **会话树** (when forks exist) /
**回到分叉点再试**. Bookmarks via API; tree nodes show bookmark counts.

```http
POST /api/sessions/{id}/refork   # new sibling under same parent at fork_point
```

## Prompt templates

```
.nlm/prompts/<name>.md
plugins_volume/prompts/<name>.md
```

Slash expansion in chat: `/review src/app.py` → full prompt body with `$FILE` filled.
Command Palette → **Prompt 模板** lists templates and inserts `/name $VARS`.

```http
GET /api/prompts?cwd=
POST /api/prompts/expand  { "cwd": "...", "text": "/review path" }
```

Built-ins: `plugins_volume/prompts/review.md`, `commit-msg.md`.

## Presets

```
.nlm/presets/<name>.json
~/.nlm/presets/<name>.json
plugins_volume/presets/<name>.json
```

Fields: `model`, `provider`, `permission_preset`, `reasoning_effort`,
`active_tools`, `system_prompt_append`.

Built-ins: `code-review`, `quick-ask`, `docs-write`.

Command Palette → **预设 Presets** applies via interaction patch (tools + permission).
**清除工具收敛** clears session `active_tools`.

```http
GET /api/presets?cwd=
PATCH /api/sessions/{id}/interaction  { "preset_name": "code-review", "cwd": "..." }
```

## Pre-tool hooks

```
<cwd>/.nlm/hooks/pre_tool.py
plugins_volume/hooks/pre_tool.py
```

```python
def pre_tool(ctx: dict) -> dict | None:
    # ctx: tool, base, arguments, plugin_id, session_id, task_id, cwd
    return {"block": True, "reason": "..."}  # or {"arguments": {...}}
```

Default sample at `plugins_volume/hooks/pre_tool.py` blocks writes to `.env` / key files.

## Compaction ledger

When context is compacted, the agent emits `task.status` with
`kind=compaction` + ledger fields, and appends to
`session.compaction_ledger`. Trajectory shows compaction status lines.

## JSONL mode

```bash
nlm chat --jsonl --cwd PATH "your prompt"
```

Prints every SSE event as one JSON line (CI / eval / replay).
