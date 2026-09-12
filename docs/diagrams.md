# Diagrams in chat (Mermaid & Draw.io)

The workbench renders fenced diagrams in assistant messages.

## Formats

| Fence | When to use | Engine |
|-------|-------------|--------|
| ` ```mermaid ` | Default: flows, sequences, ER, state, mind maps | Local Mermaid v11 |
| ` ```drawio ` / ` ```diagrams ` / ` ```mxfile ` | Precise layout, swimlanes, richer architecture boards | **Offline SVG preview** by default; optional local `/drawio/` embed or remote diagrams.net |
| ` ```xml ` | Only if body is `<mxfile>` / `<mxGraphModel>` | Same as Draw.io |

Agent guidance lives in the kernel system prompt (`## Diagrams`): the model **chooses** Mermaid vs Draw.io by complexity.

### Mermaid

- Sanitized locally (broken arrows like `-. -->` → `-.->`).
- Optional `/api/mermaid/repair` model rewrite on parse failure.
- Toolbar: fold, copy, fullscreen (pan + crisp zoom), view/source.

### Draw.io XML

Example:

````markdown
```drawio
<mxfile host="app.diagrams.net">
  <diagram name="Page-1">
    <mxGraphModel>
      <root>
        <mxCell id="0"/>
        <mxCell id="1" parent="0"/>
        <mxCell id="2" value="Hello" style="rounded=1;whiteSpace=wrap;html=1;" vertex="1" parent="1">
          <mxGeometry x="120" y="120" width="120" height="60" as="geometry"/>
        </mxCell>
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
```
````

- Toolbar: fold, copy XML, open in diagrams.net, fullscreen, view/source.
- Offline: built-in mxCell → SVG preview (no CDN). Drop a diagrams.net embed build into `web/public/drawio/` for full local viewer, or set `localStorage.nlm_drawio_embed`.
- Fast experience tier: Draw.io fences render as blocked source (Mermaid only).

## Related

- Experience tiers (Mermaid ↔ Draw.io + model strength): [experience-tiers.md](./experience-tiers.md)
- Deferred items: [deferred.md](./deferred.md)
