/**
 * Cordis-lite Canvas view registry — plugins register custom kinds via CANVAS_VIEW.
 */
import type { ComponentType } from "react";

import type { CanvasDoc } from "@/lib/canvasDoc";
import { getSlot, listSlotKeys, registerSlot, SlotNames, unregisterSlot } from "@/runtime/pluginSlots";

export type CanvasViewProps = {
  doc: CanvasDoc;
  onCommit: (body: string) => void;
  modelProvider?: string;
  modelName?: string;
  experienceTier?: string;
};

export type CanvasViewComponent = ComponentType<CanvasViewProps>;

export function registerCanvasView(key: string, component: CanvasViewComponent): void {
  const k = String(key || "").trim();
  if (!k) return;
  registerSlot(SlotNames.CANVAS_VIEW, k, component, { kind: "canvas_view" });
}

export function unregisterCanvasView(key: string): boolean {
  return unregisterSlot(SlotNames.CANVAS_VIEW, key);
}

export function getCanvasView(kind?: string | null): CanvasViewComponent | null {
  const k = String(kind || "").trim();
  if (!k) return null;
  return getSlot<CanvasViewComponent>(SlotNames.CANVAS_VIEW, k) || null;
}

export function listRegisteredCanvasViews(): string[] {
  return listSlotKeys(SlotNames.CANVAS_VIEW);
}
