# Offline Draw.io viewer

Drop a self-hosted [diagrams.net](https://github.com/jgraph/drawio) embed build here as `index.html`
(and assets). When present, **chat** prefers `/drawio/index.html?...` over remote/offline SVG.

Without this folder:

- Chat: built-in **offline SVG preview** from mxGraph cells (no network).
- **Canvas** Draw.io editor: falls back to remote `embed.diagrams.net` (editable) with offline SVG underneath until ready.

Optional override: `localStorage.nlm_drawio_embed = "https://..."` (or a same-origin path).

See [docs/diagrams.md](../../docs/diagrams.md) and [docs/canvas.md](../../docs/canvas.md).
