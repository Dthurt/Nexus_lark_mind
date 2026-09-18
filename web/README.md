# Nexus Lark Mind — Web workbench

React + TypeScript + Vite UI for the NLM workbench. Production build is written to `../web-static` and served by Adapters (`:8000`).

## Local debug (recommended)

From repo root:

```bat
scripts\dev.bat
```

This starts the Python backend (`:8000`) and Vite (`:5173`). **Open http://127.0.0.1:5173** — `/api` is proxied to the backend (SSE timeouts disabled).

See [docs/local-start.md](../docs/local-start.md).

## Scripts

```bash
npm install
npm run dev       # Vite :5173 only (backend must already be on :8000)
npm run build     # tsc + vite → ../web-static
npm test          # vitest
npm run test:e2e  # Playwright (needs backend on :8000)
npm run lint      # oxlint
```

Optional: `NLM_API_PROXY=http://127.0.0.1:8000` overrides the Vite proxy target.

## Layout

Sidebar · center Chat / Trajectory / **知识库** (+ optional **Canvas** split) · RightDock.  
See [docs/client-architecture.md](../docs/client-architecture.md), [docs/knowledge-base.md](../docs/knowledge-base.md), [docs/canvas.md](../docs/canvas.md).

## Extension docs (this folder)

| Doc | Topic |
|-----|--------|
| [tool-views.md](./tool-views.md) | `registerToolView` — tool call cards |
| [canvas-views.md](./canvas-views.md) | `registerCanvasView` — Canvas document kinds |

## Themes

`day` / `gray` / `night` / `ocean` / `rose` — Topbar cycle; `localStorage` key `nlm-theme`.
