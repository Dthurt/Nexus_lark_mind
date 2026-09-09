# Architecture notes (Vue client)

## Cordis-lite

`web/src/runtime/createContext.js` — module composition without porting Cordis.

```js
const ctx = createContext();
ctx.plugin((c) => {
  c.inject("conversation.view", () =>
    c.register("conversation.view", "list", { id: "chat", meta: { label: "Chat" } })
  );
});
```

Builtin modules: `web/src/runtime/modules/index.js`.

## Trajectory dual view

Topbar **Chat | Trajectory** toggles center projection:

- Chat → `useChatTimeline` bubbles
- Trajectory → `useTrajectory` event ledger (turns / tools / status)

Same SSE feed; separate stores.

## Stronger right dock

`useRightDock` + `RightDock.vue`:

- push track collapse
- tabs: plugins / activity / usage / inspector
- optional **split** (2 panes, drag ratio)
- open inspector from Trajectory / activity rows

## Still not ported from DSH

Full Cordis fiber graph, dockkit float/undo tree, plugin marketplace — see historical notes; current stack uses these lite contracts instead.
