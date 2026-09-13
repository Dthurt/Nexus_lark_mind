# Nexus Lark Mind — Web workbench

React + TypeScript + Vite UI for the NLM workbench. Production build is written to `../web-static` and served by Adapters (`:8000`).

## Scripts

```bash
npm install
npm run dev       # Vite :5173, proxies /api → :8000
npm run build     # tsc + vite → ../web-static
npm test          # vitest
npm run test:e2e  # Playwright (needs backend on :8000)
npm run lint      # oxlint
```

## Layout

Sidebar · center Chat/Trajectory (+ optional **Canvas** split) · RightDock.  
See [docs/client-architecture.md](../docs/client-architecture.md) and [docs/canvas.md](../docs/canvas.md).

## Extension docs (this folder)

| Doc | Topic |
|-----|--------|
| [tool-views.md](./tool-views.md) | `registerToolView` — tool call cards |
| [canvas-views.md](./canvas-views.md) | `registerCanvasView` — Canvas document kinds |

## Themes

`day` / `gray` / `night` / `ocean` / `rose` — Topbar cycle; `localStorage` key `nlm-theme`.

## Stack notes

- Path alias `@/` → `src/`
- UI primitives under `src/components/ui/` (Radix-based)
- Markdown / Mermaid / ECharts / Draw.io: `src/lib/markdown/`
