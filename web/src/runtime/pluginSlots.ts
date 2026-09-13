/** Cordis-lite style UI extension slots (not a full Cordis fiber graph). */

export const SlotNames = {
  TOOL_CALL_VIEW: "tool.call.view",
  COMPOSER_ACTION: "composer.action",
  DOCK_PANEL: "dock.panel",
  /** Canvas document view contributions (P2+). */
  CANVAS_VIEW: "canvas.view",
} as const;

export type SlotName = (typeof SlotNames)[keyof typeof SlotNames] | string;

export type SlotRegistration<T = unknown> = {
  slot: SlotName;
  key: string;
  value: T;
  meta?: Record<string, unknown>;
};

const slots = new Map<string, Map<string, SlotRegistration>>();

function bucket(slot: SlotName): Map<string, SlotRegistration> {
  const s = String(slot || "").trim();
  if (!slots.has(s)) slots.set(s, new Map());
  return slots.get(s)!;
}

/** Register a keyed contribution into a named slot. */
export function registerSlot<T = unknown>(
  slot: SlotName,
  key: string,
  value: T,
  meta?: Record<string, unknown>,
): void {
  const k = String(key || "").trim();
  if (!k) return;
  bucket(slot).set(k, { slot, key: k, value, meta });
}

export function unregisterSlot(slot: SlotName, key: string): boolean {
  return bucket(slot).delete(String(key || "").trim());
}

export function getSlot<T = unknown>(slot: SlotName, key: string): T | undefined {
  const hit = bucket(slot).get(String(key || "").trim());
  return hit ? (hit.value as T) : undefined;
}

export function listSlotKeys(slot: SlotName): string[] {
  return Array.from(bucket(slot).keys()).sort();
}

export function listSlotEntries<T = unknown>(slot: SlotName): SlotRegistration<T>[] {
  return Array.from(bucket(slot).values()) as SlotRegistration<T>[];
}

export function listAllSlots(): { slot: string; keys: string[] }[] {
  return Array.from(slots.entries())
    .map(([slot, map]) => ({ slot, keys: Array.from(map.keys()).sort() }))
    .sort((a, b) => a.slot.localeCompare(b.slot));
}
