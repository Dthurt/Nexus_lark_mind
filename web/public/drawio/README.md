# Offline Draw.io viewer

Drop a self-hosted [diagrams.net](https://github.com/jgraph/drawio) embed build here as `index.html`
(and assets). When present, chat prefers `/drawio/index.html?...` over the remote CDN.

Without this folder, NLM uses the **built-in offline SVG preview** parsed from mxGraph cells
(no network required for viewing).

Optional override: `localStorage.nlm_drawio_embed = "https://..."`.
