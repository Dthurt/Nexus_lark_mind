import type { ComponentType } from "react";

import {
  GenericToolCard,
  type GenericToolCardProps,
  type ToolCardItem,
} from "./GenericToolCard";
import { getSlot, listSlotKeys, registerSlot, SlotNames, unregisterSlot } from "@/runtime/pluginSlots";

export type ToolViewProps = GenericToolCardProps;
export type ToolViewComponent = ComponentType<ToolViewProps>;

/** Register a custom tool call view keyed by tool name / openai_name. */
export function registerToolView(key: string, component: ToolViewComponent): void {
  const k = String(key || "").trim();
  if (!k) return;
  registerSlot(SlotNames.TOOL_CALL_VIEW, k, component, { kind: "tool_view" });
}

export function unregisterToolView(key: string): boolean {
  return unregisterSlot(SlotNames.TOOL_CALL_VIEW, key);
}

export function listRegisteredToolViews(): string[] {
  return listSlotKeys(SlotNames.TOOL_CALL_VIEW);
}

/** Resolve a registered tool view, falling back to GenericToolCard. */
export function getToolView(
  name?: string | null,
  openaiName?: string | null,
): ToolViewComponent {
  for (const key of [openaiName, name]) {
    if (!key) continue;
    const hit = getSlot<ToolViewComponent>(SlotNames.TOOL_CALL_VIEW, key);
    if (hit) return hit;
  }
  return GenericToolCard;
}

/** Render helper: pick view from item fields and mount it. */
export function ToolCallView({
  item,
  nested,
  highlighted,
  onInspect,
  onOpenChange,
  onStop,
}: ToolViewProps) {
  const View = getToolView(item.name, item.openaiName);
  return (
    <View
      item={item}
      nested={nested}
      highlighted={highlighted}
      onInspect={onInspect}
      onOpenChange={onOpenChange}
      onStop={onStop}
    />
  );
}

export type { ToolCardItem };
export { GenericToolCard };
export { SlotNames };
