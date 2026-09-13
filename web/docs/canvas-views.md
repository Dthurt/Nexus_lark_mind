# Extending Canvas views

Register a custom React view for a Canvas document `kind`. Builtin kinds (`mermaid`, `echarts`, `drawio`, `table`, `markdown`, `delivery`) are registered from `src/components/canvas/registerBuiltinCanvasViews.tsx` (imported by `main.tsx`).

Full product docs: [docs/canvas.md](../../docs/canvas.md).

## API

```ts
import { registerCanvasView } from "@/components/canvas/canvasRegistry";
import type { CanvasViewProps } from "@/components/canvas/canvasRegistry";

function MyView({ doc, onCommit, modelProvider, modelName, experienceTier }: CanvasViewProps) {
  return (
    <div>
      <h3>{doc.title}</h3>
      <textarea
        defaultValue={doc.body}
        onBlur={(e) => onCommit(e.target.value)}
      />
    </div>
  );
}

registerCanvasView("my_kind", MyView);
```

| Helper | Role |
|--------|------|
| `registerCanvasView(key, Component)` | `registerSlot("canvas.view", key, …)` |
| `getCanvasView(kind)` | Resolve component or `null` |
| `listRegisteredCanvasViews()` | Keys for Extensions panel |
| `unregisterCanvasView(key)` | Remove |

`CanvasPane` does:

```ts
const View = getCanvasView(active.kind) || MarkdownCanvasView;
return <View doc={active} onCommit={updateActiveBody} … />;
```

## Props

```ts
type CanvasViewProps = {
  doc: CanvasDoc;           // id, title, kind, body, updatedAt, source?
  onCommit: (body: string) => void;  // persist into session Canvas store
  modelProvider?: string;
  modelName?: string;
  experienceTier?: string;
};
```

Use shared chrome when useful: `CanvasEditorShell` + `useSyncedDraft` under `src/components/canvas/`.

## Opening a custom kind from UI

```ts
window.dispatchEvent(
  new CustomEvent("nlm-canvas-open", {
    detail: {
      kind: "my_kind",
      title: "Board",
      body: JSON.stringify({ columns: [] }),
      dedupeKey: "my_kind:board-1",
    },
  }),
);
```

## Agent `open_canvas`

Builtin tool kinds are an enum on the server. Custom kinds opened only from the browser need a schema update in `src/core_kernel/plugin_runtime/workspace_tools.py` if the model should choose them.

## Inspect

Dock → **插件 → 扩展槽** lists `canvas.view` keys. See also [tool-views.md](./tool-views.md) for the tool-card registry pattern.
