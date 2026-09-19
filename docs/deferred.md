# Deferred / superseded

Original “full DSH port” items:

| Item | Status in Nexus |
|------|-----------------|
| Plugin marketplace | **Partial** — local Dock 市场 + `plugin_catalog/` + `/api/plugins/marketplace`; public remote catalog still deferred |
| Cordis module graph | **Superseded** by Cordis-lite slots (`pluginSlots.ts` + `registerToolView` / `registerCanvasView`) |
| dockkit split tree | **Superseded** by RightDock 2-pane split + tabs |
| Trajectory dual view | **Done** (Chat \| Trajectory ring) |
| Experience tier slider (Codex-like) | **Done** (Wave D) — Composer + session `experience_tier` + Fast Draw.io gate |
| Offline / bundled Draw.io viewer | **Partial** — offline SVG preview by default; optional `/drawio/` bundle ([diagrams.md](./diagrams.md)) |
| Feishu cards for tool approval / ask_user | **Done** (Wave E) — interactive cards + gate resolve |
| Feishu Card Kit 2.0 (stream / think / select / chart) | **Done** — [channels.md](./channels.md) |
| Local KB + WeKnora / WeMM bridge | **Done** — [knowledge-base.md](./knowledge-base.md); local Wiki + graph distill **done**; GraphRAG community retrieval still out of scope |
| `nlm` missing-Python prompt / install | **Done** — [local-start.md](./local-start.md) |
| Feishu plan review cards | **Done** — `build_plan_review_card` + `task.plan_review` |
| Delivery artifact (Plan→Diagram→Changes) | **Done** — RightDock Delivery + session file |
| Full Anthropic Messages path | **Done** — builtin + custom `anthropic-messages` providers; thinking on supporting models |
| Agent Teams DAG / durable mailbox | **Done** (experimental) — file/KV mailbox + DAG + Teams UI ([agent-teams.md](./agent-teams.md)) |
| Multi-backend subagents / ACP server | **Partial** — `SubagentBackend` + thin ACP HTTP bridge ([multi-backend-subagents.md](./multi-backend-subagents.md)); full ACP host deferred |
| DSH PTC mode | **Deferred** — NLM ships `run_code` instead ([workspaces.md](./workspaces.md)) |
| Headless / Python SDK | **Done** (Wave F) — [headless-sdk.md](./headless-sdk.md) |
| Playwright e2e | **Done** — `web/e2e` smoke (`npm run test:e2e`, needs :8000) |
| **Canvas P1–P3** (side pane + editors + Agent/disk + `CANVAS_VIEW`) | **Done** — see **[canvas.md](./canvas.md)** |
| Infinite freeform whiteboard / node graph | **Deferred** (out of product scope for Canvas) |
| Canvas sync edits back into historical chat bubbles | **Deferred** (Canvas is a separate durable copy) |
| `.nlm/canvases` write on SSH workspaces | **Deferred** (local cwd only, same as Delivery) |

Public plugin marketplace remains out of scope until there is a signing + distribution story beyond local HMAC.
