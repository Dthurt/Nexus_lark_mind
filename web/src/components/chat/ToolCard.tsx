import {
  ToolCallView,
  type ToolCardItem,
  type ToolViewProps,
} from "@/components/tools/toolRegistry";

export type ToolCardProps = ToolViewProps;

/** Resolves a registered tool view via getToolView / toolRegistry. */
export function ToolCard({ item, nested, onInspect, onOpenChange }: ToolCardProps) {
  return (
    <ToolCallView
      item={item}
      nested={nested}
      onInspect={onInspect}
      onOpenChange={onOpenChange}
    />
  );
}

export type { ToolCardItem };
export default ToolCard;
