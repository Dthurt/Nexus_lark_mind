# Interaction modes (Plan · Auto-accept · Ask · Inbox)

Claude Code–style controls for the Web workbench, plus DSH-inspired mid-turn inbox.

## Composer toggles

| Toggle | Default | Effect |
|--------|---------|--------|
| **计划** (`agent_mode=plan`) | off | Read-only tools only; agent writes a checklist plan; UI shows **接受计划并执行** |
| **自动接受** (`auto_accept`) | off | When off, `run_shell` / `write_file` / `edit_file` pause for Allow / Deny |
| **工具** | on | Existing tools-enabled flag |

Flags persist in `localStorage` (`nlm_agent_mode`, `nlm_auto_accept`) and Redis session via `PATCH /api/sessions/{id}/interaction`.

## Permission presets

Composer **+** menu → **权限**:

| Preset | Effect |
|--------|--------|
| **只读** (`read-only`) | Mutating tools (`write_file` / `edit_file` / `run_shell` …) filtered & blocked |
| **工作区可写** (`workspace-write`, default) | Mutating tools need ApprovalDock unless Accept is on |
| **全权限** (`danger-full-access`) | Accept forced on — no approval prompts |

Selecting a preset writes `permission_preset` + derived `auto_accept` via `PATCH /api/sessions/{id}/interaction`.

Paths stay sandboxed to session cwd (local + SSH); escapes raise `PermissionError`.

## Plan soft / hard

When Plan Mode is on, **Plan 硬约束** toggle:

| Mode | Effect |
|------|--------|
| **hard** (default) | Write/shell tools hidden & blocked until plan accepted |
| **soft** | Prompt guidance only — tools still available if the permission preset allows |

Persisted as `plan_enforcement` (`localStorage.nlm_plan_enforcement`).

## Busy inbox (Steer · Queue)

While a turn is running, the composer stays editable. Sending does **not** start a parallel chat — it goes to the session inbox.

| Action | Behavior |
|--------|----------|
| **Enter** (busy + draft) | Push to session inbox — default **queue** (or **steer** if toggled / `nlm_busy_enter=steer`) |
| **Ctrl/Cmd+Enter** | Flip kind for this send only (queue ↔ steer) |
| **Primary button** | Draft present → send to inbox; empty → **Stop** |
| **Busy toolbar** | Toggle **中途引导** / **排队** above the textarea |
| **QueueDock** | Lists pending items (or a hint while busy with empty inbox); **撤销** removes one |

Semantics:

- **steer（中途引导）** — claimed at the next agent **step** boundary (before the next model call); injected into the live turn. The current tool may finish first.
- **queue（排队）** — claimed after the turn **completes** successfully; starts a new task with that content (appears in chat when enqueued).

APIs:

- `GET/POST /api/sessions/{id}/inbox`
- `DELETE /api/sessions/{id}/inbox/{item_id}`
- SSE `task.inbox` (`action`: `pushed` \| `removed` \| `claimed`)

Cancel: `POST .../cancel` body `{ "keep_inbox": true }` (default) keeps pending inbox; `false` clears it.

Local preference: `localStorage.nlm_busy_enter` = `queue` \| `steer`.

## Plan mode

1. User enables **计划**.
2. Agent may use: `glob`, `grep`, `list_dir`, `read_file`, `ask_user`, `open_canvas`.
3. Writes/shell are blocked in the runner (not only by prompt).
4. When the turn ends with a text plan, SSE `task.plan_ready` marks the assistant bubble.
5. **接受计划并执行** → `POST /api/sessions/{id}/accept-plan` flips to `agent`, enqueues an execute turn.

## Tool approval

SSE: `task.tool_approval` → `ApprovalDock`（输入框上方审批条）。

- **仅允许这次** — 只放行本次调用  
- **本会话自动接受** — 放行并开启 Accept（后续请求带 `auto_accept`）  
- **拒绝** — 合成工具错误回传模型  
- 超时按工具类型自动拒绝（shell 60s / 写编辑 45s / 其他 30s） 

Resolve: `POST /api/sessions/{id}/approvals` → Kernel `POST /rpc/gates/resolve`.

## Ask user

Tool: `ask_user` (workspace plugin; handled in `agent_runner`, not invoked as FS).

```json
{
  "title": "可选标题",
  "questions": [
    {
      "id": "q1",
      "prompt": "用哪套方案？",
      "options": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
      "allow_multiple": false,
      "allow_custom": true
    }
  ]
}
```

SSE: `task.ask_user` → `AskUserForm` (multi-question, radio/checkbox, custom text).  
Resolve: `POST /api/sessions/{id}/ask-answers`.

## Gates

Pending approvals/asks block inside the Kernel process (`src/core_kernel/user_gate.py`),
with a Redis/KV **mirror** so orphans can be detected after a Kernel restart.

- Live waiters use in-process Futures.
- Mirror keys: `gate:{call_id}` + session index `gates:sess:{session_id}`.
- If the Kernel restarts mid-gate, `await_gate` / resolve clears the mirror and returns `deny` (`kernel_restart`).
- Session cancel still calls `POST /rpc/gates/deny-session`.

## Long-session reliability (Wave C)

| Concern | Behavior |
|---------|----------|
| **Context overflow** | Detect provider overflow errors → aggressive compact → **one** model retry |
| **SSE gaps** | Orchestrator appends events to a ring buffer; `GET /api/chat/stream?session_id=&after=` replays missed `event_id`s; client reconnects with last cursor |
| **Subagents** | Continuable snapshots in KV (`subagent:{id}`); `list_agents` / `send_message` hydrate after restart |
| **Chat DOM** | Timeline renders the last ~60 blocks; **加载更早的消息** expands the window |

## Information architecture (Wave D)

| Control | Where | Effect |
|---------|-------|--------|
| **Turn process fold** | After `finalizeBot` | Mid-turn thinking + tools collapse to 「思考片刻 · N 工具」 |
| **体验档** `experience_tier` | Composer + session | Constrains Mermaid vs Draw.io in the system prompt |
| **推理强度** `reasoning_effort` | Composer + session | Passed on `ModelRequest` (OpenAI-compat `reasoning_effort`) |
| **Jobs** tab | RightDock | Running / recent tools & subagents from the timeline |
| **Delivery** tab | RightDock | Plan → Diagrams → Code changes audit doc (auto on plan approve) |
| **Canvas** pane | Topbar / toolbars / `open_canvas` | Editable side artifacts (Chat∥Canvas); see [canvas.md](./canvas.md) |
| **@ context** | Composer `@` / chips | Attach files/dirs into the model prompt; [context-and-diff.md](./context-and-diff.md) |
| **Diff review** | Above composer after write/edit | Accept / revert applied mutations; [context-and-diff.md](./context-and-diff.md) |

## Delivery artifact (Plan → Diagram → Changes)

When you **批准并执行** a plan (gate path or legacy accept-plan):

1. NLM builds a markdown **Delivery** doc: plan body, extracted Mermaid/Draw.io fences, mutation tool summary (path · bytes/lines · replace hints).
2. Posts it via `POST /api/sessions/{id}/delivery` → chat file card **and** local `{cwd}/.nlm/deliveries/*.md`.
3. Opens RightDock **Delivery**; auto-syncs `write_file` / `edit_file` / … from `plugin-calls` after the turn.
4. Optional: Delivery panel **Canvas** opens the same markdown in the side Canvas pane for comfortable reading/editing ([canvas.md](./canvas.md)).

Demo: enable **计划** → ask for a feature plan with a Mermaid flow → approve → open `.nlm/deliveries/` in the workspace → sync after edits → optionally **Canvas**.

**Canvas vs Delivery:** Delivery is the plan-execution audit trail; Canvas is a general multi-tab side document (diagrams, tables, notes) that Agent can open with `open_canvas` and optionally persist under `.nlm/canvases/`.

## Feishu

Interactive cards for **tool approval**, **ask_user**, and **plan_review** are shipped:

- First message in a Feishu conversation **requires** picking Provider + model via cards (from the configured catalog). The choice is stored on the session for later turns; send `切换模型` or `/model` to re-pick.
- If no Provider is configured, Feishu sends a setup card (Web Settings → model providers) instead of falling into demo-mode echo.
- Bus events `task.tool_approval` / `task.ask_user` / `task.plan_review` → Feishu interactive cards
- Card actions resolve via the same Kernel `/rpc/gates/resolve` path as the Web workbench
- Plan review actions: 批准并执行 / 继续规划 / 稍后自己说
- Approval timeouts match Web (`src/common/approval_timeouts.py` ↔ `web/src/lib/approvalTimeout.ts`)

Streaming reply cards use **Card JSON 2.0**: one message is patched in place (debounced), tool/KB progress and citations render as card sections, errors are warning cards (no stack traces). Retry / 切换模型 / 清空会话 are schema 2.0 callback buttons.

See also: [channels.md](./channels.md), [experience-tiers.md](./experience-tiers.md), [canvas.md](./canvas.md), [diagrams.md](./diagrams.md), [deferred.md](./deferred.md), [subagents.md](./subagents.md).
