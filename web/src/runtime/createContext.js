/**
 * Cordis-lite: Vue-native module composition (inspired by DSH Cordis, not a port).
 *
 * Plugins call apply(ctx). ctx.slots mirrors @nlm/ui slots.
 * ctx.inject(name, factory) scopes registrations to the plugin lifetime.
 */
import { uiSlots, createSlotRegistry, SlotNames } from "@nlm/ui";

export function createContext(options = {}) {
  const slots = options.slots || uiSlots;
  const services = new Map();
  const disposers = [];
  let disposed = false;

  const ctx = {
    slots,
    SlotNames,

    provide(name, value) {
      services.set(name, value);
      return ctx;
    },

    get(name, fallback = undefined) {
      if (services.has(name)) return services.get(name);
      return fallback;
    },

    /** Register entries; returns disposer. Scoped via inject(). */
    register(name, kind, entry) {
      const dispose = slots.register(name, kind, entry);
      disposers.push(dispose);
      return dispose;
    },

    /**
     * Cordis-style: inject(slotName, () => register(...))
     * Runs factory immediately; disposer tied to this context.
     */
    inject(slotName, factory) {
      const out = factory();
      if (typeof out === "function") disposers.push(out);
      return out;
    },

    plugin(applyFn) {
      if (typeof applyFn !== "function") throw new Error("plugin apply must be a function");
      applyFn(ctx);
      return ctx;
    },

    dispose() {
      if (disposed) return;
      disposed = true;
      while (disposers.length) {
        try {
          disposers.pop()();
        } catch {
          /* ignore */
        }
      }
      services.clear();
    },
  };

  return ctx;
}

export { createSlotRegistry, SlotNames, uiSlots };
