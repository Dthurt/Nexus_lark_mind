# Subagents (DSH-inspired)

Nexus Lark Mind can delegate work to nested **subagents** with live streaming in the chat UI.

## Who decides

**The parent agent decides** whether to spawn a subagent, based on the task (isolation, multi-step focus, parallel tracks). Users may explicitly ask for a subagent; that is optional. Do not treat subagents as a user-triggered mode.

| Use a subagent | Do it yourself |
|----------------|----------------|
| Bounded multi-step research / refactor / verify pass | Single grep, read, or edit |
| Work that should not clutter the parent turn | Trivial one-shot answers |
| Parallelizable slices while you orchestrate | Anything needing constant user back-and-forth in the same turn |

## Tools

| Tool | Role |
|------|------|
| `subagent` | Fresh child (no parent transcript). Args: `description`, `prompt` |
| `subagent_fork` | Child inherits completed parent turns. Args: `description`, `prompt` |
| `send_message` | Continue an idle/ready child (`agent_id`, `message`) |
| `interrupt_agent` | Cancel current child turn (`agent_id`) |
| `list_agents` | List children for this session (`scope`: children\|descendants) |

Plugin id: `builtin.subagent` (enabled by default). OpenAI tool names are short (same as workspace tools).

## Streaming UX

- Parent chat shows a **purple SUB** card (distinct from gold tool chips).
- Card is **folded by default**; expand to see input prompt, streamed output, and child tool rows.
- SSE event: `task.subagent` with `phase`: `start` \| `delta` \| `tool_call` \| `tool_result` \| `end`.
- Final parent tool result still returns `{ kind, subagent_id, output, … }` for the model.

## Limits

- Max nesting depth: **3**
- Children below max depth may spawn further subagents; at max depth those tools are hidden.

## Notes

- Same model gateway + workspace cwd/SSH meta as parent.
- Continuable children are snapshotted to Redis/KV (`subagent:{id}` + session index).
  After Kernel restart, `list_agents` / `send_message` **hydrate** idle children (mid-run
  `running` snapshots are treated as `idle`). Live cancel still needs the in-process
  `cancel_event` (interrupt after restart only marks status).
- Experimental **Agent Teams** mailbox: [agent-teams.md](./agent-teams.md).
- Multi-backend / ACP: [multi-backend-subagents.md](./multi-backend-subagents.md).
