# Skills / Fork / Hooks / Compaction ledger / JSONL

Nexus Lark Mind borrows several **extension patterns** from Pi-style agent harnesses
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
---
# body …
```

- System prompt lists **name + description + path** only.
- Model should `read_file` the skill path when relevant.
- User / Command Palette can insert `/skill:<name> …`.
- API: `GET /api/skills?cwd=<path>`

Example skill ships at `.nlm/skills/verify-change/SKILL.md` (repo root).

## Session fork

```http
POST /api/sessions/{id}/fork
{ "until_index": 12, "title": "Try plan B" }
```

Copies messages (optionally truncated) into a new session, preserving workspace
and interaction prefs. Web: Command Palette → **从此会话分叉**.

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
