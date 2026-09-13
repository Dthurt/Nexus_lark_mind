# Client architecture (React workbench)

The Web UI is **React + TypeScript + Vite** under `web/` (built assets land in `web-static/` for Adapters). Older Vue notes no longer apply.

## Shell layout

```
nlm-app
├── Sidebar (sessions / workspaces)
├── main.nlm-workspace
│   ├── Topbar (Chat|Trajectory ring, Canvas toggle, theme, …)
│   └── nlm-chat-panel
│       ├── [optional] nlm-center-split
│       │   ├── nlm-chat-column (messages + docks + Composer)
│       │   └── CanvasPane
│       └── or flat chat stack when Canvas closed
└── RightDock (plugins / Delivery / activity / usage / inspector / …)
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

Topbar **Chat | Trajectory** (`ViewRing`):

- Chat → `useChatTimeline` bubbles  
- Trajectory → `useTrajectory` event ledger  

Same SSE feed; separate stores.

## Right dock

`useRightDock` + `RightDock`:

- Collapse / expand rail  
- Tabs: plugins (市场 / 扩展槽), Delivery, activity, jobs, usage, inspector, …  
- Optional 2-pane split  

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
