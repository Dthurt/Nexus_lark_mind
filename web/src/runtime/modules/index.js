/**
 * Built-in Cordis-lite modules. Each exports apply(ctx).
 */
import { SlotNames } from "@nlm/ui";

/** Registers conversation view contributions (chat + trajectory). */
export function conversationViewsModule(ctx) {
  ctx.inject("conversation.view", () =>
    ctx.register("conversation.view", "list", {
      id: "chat",
      order: 10,
      meta: { label: "Chat" },
    })
  );
  ctx.inject("conversation.view", () =>
    ctx.register("conversation.view", "list", {
      id: "trajectory",
      order: 20,
      meta: { label: "Trajectory" },
    })
  );
}

/** Right dock tab kinds */
export function rightDockModule(ctx) {
  const kinds = [
    { key: "plugins", order: 10, meta: { title: "插件" } },
    { key: "activity", order: 20, meta: { title: "本回合" } },
    { key: "usage", order: 30, meta: { title: "用量" } },
    { key: "inspector", order: 40, meta: { title: "检查器" } },
  ];
  for (const k of kinds) {
    ctx.inject(SlotNames.RAIL_TAB || "rail.tab", () =>
      ctx.register(SlotNames.RAIL_TAB || "rail.tab", "keyed", {
        id: k.key,
        key: k.key,
        order: k.order,
        meta: k.meta,
      })
    );
  }
}

export function applyBuiltinModules(ctx) {
  ctx.plugin(conversationViewsModule);
  ctx.plugin(rightDockModule);
  return ctx;
}
