/**
 * Lightweight UI slot registry (DSH-inspired, Vue-native).
 * Kinds: single | list | keyed
 */
import { markRaw, shallowRef } from "vue";

function normalizeEntry(entry) {
  if (!entry || typeof entry !== "object") {
    throw new Error("slot entry must be an object");
  }
  const id = entry.id || entry.key || "default";
  return {
    id,
    key: entry.key,
    order: entry.order ?? 0,
    component: entry.component ? markRaw(entry.component) : null,
    render: entry.render || null,
    meta: entry.meta || {},
  };
}

export function createSlotRegistry() {
  /** @type {Map<string, { kind: string, entries: import('vue').ShallowRef }>} */
  const slots = new Map();

  function ensure(name, kind) {
    let slot = slots.get(name);
    if (!slot) {
      slot = { kind, entries: shallowRef([]) };
      slots.set(name, slot);
    } else if (slot.kind !== kind) {
      throw new Error(`slot ${name} kind mismatch: ${slot.kind} vs ${kind}`);
    }
    return slot;
  }

  function sortList(entries) {
    return [...entries].sort((a, b) => (a.order ?? 0) - (b.order ?? 0) || String(a.id).localeCompare(String(b.id)));
  }

  function register(name, kind, entry) {
    const slot = ensure(name, kind);
    const next = normalizeEntry(entry);
    if (kind === "single") {
      slot.entries.value = [next];
    } else if (kind === "list") {
      const rest = slot.entries.value.filter((e) => e.id !== next.id);
      slot.entries.value = sortList([...rest, next]);
    } else if (kind === "keyed") {
      const rest = slot.entries.value.filter((e) => e.key !== next.key && e.id !== next.id);
      slot.entries.value = [...rest, next];
    } else {
      throw new Error(`unknown slot kind: ${kind}`);
    }
    return () => unregister(name, next.id, next.key);
  }

  function unregister(name, id, key) {
    const slot = slots.get(name);
    if (!slot) return;
    slot.entries.value = slot.entries.value.filter((e) => {
      if (key != null) return e.key !== key;
      return e.id !== id;
    });
  }

  function resolveSingle(name) {
    const slot = slots.get(name);
    return slot?.entries.value[0] || null;
  }

  function resolveList(name) {
    const slot = slots.get(name);
    return slot ? sortList(slot.entries.value) : [];
  }

  function resolveKeyed(name, key) {
    const slot = slots.get(name);
    if (!slot) return null;
    return slot.entries.value.find((e) => e.key === key) || null;
  }

  function clear(name) {
    const slot = slots.get(name);
    if (slot) slot.entries.value = [];
  }

  return {
    register,
    unregister,
    resolveSingle,
    resolveList,
    resolveKeyed,
    clear,
    /** for debugging */
    _slots: slots,
  };
}

/** App-wide registry */
export const uiSlots = createSlotRegistry();

/** Well-known slot names */
export const SlotNames = {
  TOOL_CALL_VIEW: "tool.call.view",
  RAIL_TAB: "rail.tab",
};
