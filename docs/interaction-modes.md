# Interaction modes (Plan · Auto-accept · Ask)

Claude Code–style controls for the Web workbench.

## Composer toggles

| Toggle | Default | Effect |
|--------|---------|--------|
| **计划** (`agent_mode=plan`) | off | Read-only tools only; agent writes a checklist plan; UI shows **接受计划并执行** |
| **自动接受** (`auto_accept`) | off | When off, `run_shell` / `write_file` / `edit_file` pause for Allow / Deny |
| **工具** | on | Existing tools-enabled flag |

Flags persist in `localStorage` (`nlm_agent_mode`, `nlm_auto_accept`) and Redis session via `PATCH /api/sessions/{id}/interaction`.

## Plan mode

1. User enables **计划**.
2. Agent may use: `glob`, `grep`, `list_dir`, `read_file`, `ask_user`.
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

Pending approvals/asks block inside the Kernel process (`src/core_kernel/user_gate.py`).  
Session cancel calls `POST /rpc/gates/deny-session` so waiters do not hang.

## Feishu

Interactive cards for approval/ask are **deferred**; Web is the supported channel for these flows.

See also: [experience-tiers.md](./experience-tiers.md), [deferred.md](./deferred.md).
