# Deferred / superseded

Original “full DSH port” items:

| Item | Status in Nexus |
|------|-----------------|
| Cordis module graph | **Superseded** by Cordis-lite (`web/src/runtime/createContext.js`) |
| dockkit split tree | **Superseded** by RightDock 2-pane split + tabs |
| Trajectory dual view | **Done** (Chat \| Trajectory ring) |
| Plugin marketplace | **Partial** — local package install + sha256/HMAC ([plugin-packaging.md](./plugin-packaging.md)); public catalog still deferred |
| Experience tier slider (Codex-like) | **Done** (Wave D) — Composer + session `experience_tier` + Fast Draw.io gate |
| Offline / bundled Draw.io viewer | **Partial** — offline SVG preview by default; optional `/drawio/` bundle ([diagrams.md](./diagrams.md)) |
| Feishu cards for tool approval / ask_user | **Done** (Wave E) — interactive cards + gate resolve |
| Feishu plan review cards | **Done** — `build_plan_review_card` + `task.plan_review` |
| Delivery artifact (Plan→Diagram→Changes) | **Done** — RightDock Delivery + session file |
| Full Anthropic Messages path | **Done** — builtin + custom `anthropic-messages` providers; thinking on supporting models |
| Agent Teams DAG / durable mailbox | **Done** (experimental) — file/KV mailbox + DAG + Teams UI ([agent-teams.md](./agent-teams.md)) |
| Multi-backend subagents / ACP server | **Partial** — `SubagentBackend` + thin ACP HTTP bridge ([multi-backend-subagents.md](./multi-backend-subagents.md)); full ACP host deferred |
| DSH PTC mode | **Deferred** — NLM ships `run_code` instead ([workspaces.md](./workspaces.md)) |
| Headless / Python SDK | **Done** (Wave F) — [headless-sdk.md](./headless-sdk.md) |
| Playwright e2e | **Done** — `web/e2e` smoke (`npm run test:e2e`, needs :8000) |

Public plugin marketplace remains out of scope until there is a signing + distribution story beyond local HMAC.
