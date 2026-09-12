import type { ComponentType } from "react";

import {
  GenericToolCard,
  type GenericToolCardProps,
  type ToolCardItem,
} from "./GenericToolCard";

export type ToolViewProps = GenericToolCardProps;
export type ToolViewComponent = ComponentType<ToolViewProps>;

const toolViews = new Map<string, ToolViewComponent>();

/** Register a custom tool call view keyed by tool name / openai_name. */
export function registerToolView(key: string, component: ToolViewComponent): void {
  const k = String(key || "").trim();
  if (!k) return;
  toolViews.set(k, component);
}

/** Resolve a registered tool view, falling back to GenericToolCard. */
export function getToolView(
  name?: string | null,
  openaiName?: string | null,
): ToolViewComponent {
  for (const key of [openaiName, name]) {
    if (!key) continue;
    const hit = toolViews.get(key);
    if (hit) return hit;
  }
  return GenericToolCard;
}

/** Render helper: pick view from item fields and mount it. */
export function ToolCallView({
  item,
  nested,
  onInspect,
  onOpenChange,
  onStop,
}: ToolViewProps) {
  const View = getToolView(item.name, item.openaiName);
  return (
    <View
      item={item}
      nested={nested}
      onInspect={onInspect}
      onOpenChange={onOpenChange}
      onStop={onStop}
    />
  );
}

export type { ToolCardItem };
export { GenericToolCard };
