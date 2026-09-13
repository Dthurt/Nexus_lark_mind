# Extending tool call views

Register a custom React view for a tool name (or OpenAI short name):

```ts
import { registerToolView } from "@/components/tools/toolRegistry";
import { MyToolCard } from "./MyToolCard";

registerToolView("web_search", MyToolCard);
registerToolView("my_plugin_tool", MyToolCard);
```

`getToolView(name, openaiName)` resolves the map and falls back to `GenericToolCard`.

Builtin registrations live in `src/components/tools/registerBuiltinTools.ts` and are imported from `main.tsx` (includes workspace tools and `open_canvas`).

Shared chrome for compact chips: `src/components/tools/ToolChipShell.tsx`.

## Related

- Canvas document views (different slot): [canvas-views.md](./canvas-views.md)
- Product / Agent Canvas: [docs/canvas.md](../../docs/canvas.md)
- Slots overview: [docs/plugins.md](../../docs/plugins.md)
