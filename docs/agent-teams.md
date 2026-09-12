# Agent Teams

Experimental agent↔agent mailbox + lightweight DAG. Enable tools with:

```env
NLM_EXPERIMENTAL_TEAMS=true
```

## Mailbox (durable)

| Tool | Role |
|------|------|
| `team_send` | Post `{team_id, to_id, payload}` (`to_id` may be `*`) |
| `team_recv` | Claim pending messages for `agent_id` |

Storage (best-effort, survives restart):

1. `data/teams/{team_id}.json` file snapshot
2. Broker KV `team:mbox:{team_id}` (memory:// or Redis, TTL 7d)

Cap ~200 msgs / team. Default `team_id = session_id`.

## DAG

Simple dependency graph (not a full workflow engine):

- `POST /api/teams/{team_id}/dag` — add node `{label, depends_on?}`
- `POST /api/teams/{team_id}/dag/{node_id}/mark` — `{status: done|failed|running|…}`
- Ready nodes = all deps `done`

Persisted under `data/teams/{team_id}.dag.json`.

## UI

Right dock **Teams** tab: agents topology, mailbox tail, DAG list (`GET /api/teams/{team_id}`).

## Not included (yet)

- Cross-process multi-backend teams (see [multi-backend-subagents.md](./multi-backend-subagents.md))
- Full visual DAG editor

Default remains classic parent→subagent tools (`subagent` / `send_message`).
