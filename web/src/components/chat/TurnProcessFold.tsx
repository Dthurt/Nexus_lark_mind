import { useMemo, useRef, useState } from "react";
import { ChevronRight } from "lucide-react";

import { ThinkingFold } from "@/components/chat/ThinkingFold";
import { ToolCallGroup } from "@/components/chat/ToolCallGroup";
import { SubagentCard } from "@/components/chat/SubagentCard";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import type { TimelineItem } from "@/hooks/useChatTimeline";
import { cn } from "@/lib/utils";

export type TurnProcessFoldProps = {
  summary: string;
  reasoning?: string;
  tools?: TimelineItem[];
  subagents?: TimelineItem[];
  highlightCallId?: string | null;
  onInspectTool?: (activityId: string) => void;
  onStopTool?: (callId?: string) => void;
  className?: string;
};

/** Collapsed mid-turn process (thinking + tools) after the turn completes. */
export function TurnProcessFold({
  summary,
  reasoning = "",
  tools = [],
  subagents = [],
  highlightCallId = null,
  onInspectTool,
  onStopTool,
  className,
}: TurnProcessFoldProps) {
  const userTouchedRef = useRef(false);
  const [open, setOpen] = useState(false);
  const hasBody = !!(reasoning || "").trim() || tools.length > 0 || subagents.length > 0;

  const handleOpenChange = (next: boolean) => {
    userTouchedRef.current = true;
    setOpen(next);
  };

  const label = useMemo(() => summary || "本回合过程", [summary]);

  if (!hasBody) return null;

  return (
    <Collapsible open={open} onOpenChange={handleOpenChange} className={cn("w-full", className)}>
      <CollapsibleTrigger asChild>
        <button
          type="button"
          className={cn(
            "flex w-full items-center gap-1.5 rounded-md px-1.5 py-1",
            "text-left text-[12px] text-muted-foreground hover:bg-muted/40 hover:text-foreground",
          )}
        >
          <ChevronRight
            className={cn("size-3.5 shrink-0 transition-transform", open && "rotate-90")}
          />
          <span className="font-medium">{label}</span>
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent className="mt-1.5 flex flex-col gap-1.5 pl-1">
        {(reasoning || "").trim() ? <ThinkingFold text={reasoning} /> : null}
        {tools.length > 0 ? (
          <ToolCallGroup
            tools={tools as any}
            highlightCallId={highlightCallId}
            onInspect={onInspectTool}
            onStop={onStopTool}
            flat
          />
        ) : null}
        {subagents.map((item) => (
          <SubagentCard
            key={item.id}
            item={item as any}
            onInspect={onInspectTool}
            onStop={onStopTool}
          />
        ))}
      </CollapsibleContent>
    </Collapsible>
  );
}

export default TurnProcessFold;
