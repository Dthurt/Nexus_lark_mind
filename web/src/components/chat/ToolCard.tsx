import {
  ToolCallView,
  type ToolCardItem,
  type ToolViewProps,
} from "@/components/tools/toolRegistry";

export type ToolCardProps = ToolViewProps;

/** Resolves a registered tool view via getToolView / toolRegistry. */
export function ToolCard({ item, nested, onInspect, onOpenChange, onStop }: ToolCardProps) {
  return (
    <ToolCallView
      item={item}
      nested={nested}
      onInspect={onInspect}
      onOpenChange={onOpenChange}
      onStop={onStop}
    />
  );
}

export type { ToolCardItem };
export default ToolCard;
