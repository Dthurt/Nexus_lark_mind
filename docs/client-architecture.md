# Client architecture (React workbench)

The Web UI is **React + TypeScript + Vite** under `web/` (built assets land in `web-static/` for Adapters). Older Vue notes no longer apply.

## Shell layout

```
nlm-app
├── Sidebar (sessions / workspaces)
├── main.nlm-workspace
│   ├── Topbar (Chat|Trajectory|知识库 ring, Canvas toggle, KB chip, theme, …)
│   └── nlm-chat-panel
│       ├── KnowledgeView when view=knowledge (search + same-session chat)
│       ├── [optional] nlm-center-split
│       │   ├── nlm-chat-column (messages + docks + Composer + KB picker)
│       │   └── CanvasPane
│       └── or flat chat stack when Canvas closed
└── RightDock (知识库 admin / plugins / Delivery / activity / …)
```

- Canvas open → `nlm-workspace--canvas` widens the center column; grid ≈ `1fr | 42%`.
- Details: [canvas.md](./canvas.md).

## Cordis-lite slots

Not a full Cordis fiber graph. Frontend registry:

`web/src/runtime/pluginSlots.ts`

| Slot | API | Host |
|------|-----|------|
| `tool.call.view` | `registerToolView` | tool cards in chat |
| `canvas.view` | `registerCanvasView` | `CanvasPane` |
| `composer.action` / `dock.panel` | reserved | — |

Dock **插件 → 扩展槽** lists live registrations. See [plugins.md](./plugins.md), [web/docs/tool-views.md](../web/docs/tool-views.md), [web/docs/canvas-views.md](../web/docs/canvas-views.md).

## Trajectory dual view

Topbar **对话 | 知识库 | 轨迹** (`ViewRing`):

- Chat → `useChatTimeline` bubbles  
- Trajectory → `useTrajectory` event ledger  

Same SSE feed; separate stores.

Ledger (DSH-inspired, Nexus-lite):

- **Turn groups** with sticky headers + fold-all  
- **Tool call/result merged** by `callId` (one row, duration on settle)  
- First-class **reasoning** / **subagent** rows (not only `system` status)  
- Toolbar **search** + kind filters + light **timing overview** bar  
- Click row → RightDock inspector (unchanged)

## Right dock

`useRightDock` + `RightDock`:

- Collapse / expand rail  
- Tabs: **知识库** (ingest / sync / remote import), plugins (市场 / 扩展槽), Delivery, activity, jobs, usage, inspector, …  
- Optional 2-pane split  

## Knowledge page

Topbar **知识库** (`/?view=knowledge`): left pane search / citations / body; right pane the same workbench chat bound to that KB. Composer always shows a **知识库** picker (`weknora_kb_id`; empty = local). See [knowledge-base.md](./knowledge-base.md).

Stream failures persist as `metadata.kind=error` assistant bubbles so refresh still shows them.

## Canvas (P1–P3)

Session-scoped side artifacts: multi-tab docs, editors, Agent `open_canvas`, disk `.nlm/canvases/`.

Canonical doc: **[canvas.md](./canvas.md)**.

## SSE → UI highlights

| Event | UI |
|-------|-----|
| `task.tool_call` / `task.tool_result` | Tool chips / cards |
| `task.tool_approval` | ApprovalDock |
| `task.ask_user` | Ask form |
| `task.plan_review` / `task.plan_ready` | Plan UI |
| `task.todos` | Todo strip |
| `task.canvas_open` | `nlm-canvas-open` → Canvas pane |
| `task.inbox` | QueueDock / steer |

Consumer: `web/src/hooks/useChatStream.ts`.

## Still deferred vs DSH

Full Cordis fiber graph, dockkit float/undo tree, public plugin marketplace — [deferred.md](./deferred.md).
