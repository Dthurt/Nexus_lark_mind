import { useMemo, useState } from "react";
import { ChevronRight } from "lucide-react";

import { ToolCard } from "@/components/chat/ToolCard";
import { ToolStatusBadge, ToolStopButton } from "@/components/tools/ToolStatusBadge";
import { Badge } from "@/components/ui/badge";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import type { ToolCardItem } from "@/components/tools/toolRegistry";
import { isToolPending, resolveToolStatus, statusShellClass } from "@/lib/toolStatus";
import { cn } from "@/lib/utils";

export type ToolCallGroupProps = {
  tools: ToolCardItem[];
  onInspect?: (activityId: string) => void;
  onStop?: (callId?: string) => void;
  className?: string;
};

function shortName(name?: string) {
  const raw = String(name || "tool");
  return raw.replace(/^builtin_workspace_/, "").replace(/^cli_/, "").split(".").pop();
}

export function ToolCallGroup({ tools, onInspect, onStop, className }: ToolCallGroupProps) {
  const [open, setOpen] = useState(false);

  const summaryLabel = useMemo(() => {
    const names = tools.map((t) => shortName(t.name));
    const unique: string[] = [];
    for (const n of names) {
      if (n && !unique.includes(n)) unique.push(n);
    }
    const preview = unique.slice(0, 4).join(" · ");
    const n = tools.length;
    if (n <= 1) return preview || "tool";
    return `${n} tools · ${preview}${unique.length > 4 ? "…" : ""}`;
  }, [tools]);

  const hasFail = tools.some((t) => resolveToolStatus(t) === "failed");
  const pending = tools.some((t) => isToolPending(t));
  const groupStatus = pending ? "running" : hasFail ? "failed" : "done";

  return (
    <Collapsible
      open={open}
      onOpenChange={setOpen}
      className={cn(
        "tool-group w-full max-w-full self-stretch overflow-hidden rounded-lg border transition-colors",
        statusShellClass(groupStatus as any),
        className,
      )}
    >
      <div className="flex items-center gap-1 pr-1.5">
        <CollapsibleTrigger asChild>
          <button
            type="button"
            className={cn(
              "inline-flex min-w-0 flex-1 items-center gap-1.5 px-2.5 py-1.5 text-left text-sm font-medium text-muted-foreground",
              "hover:text-foreground",
              open && "border-b border-border/40",
            )}
          >
            <ChevronRight
              className={cn("size-3.5 shrink-0 transition-transform", open && "rotate-90")}
              aria-hidden
            />
            <Badge
              variant="outline"
              className="h-5 border-border/60 bg-background/30 px-1.5 font-mono text-[10px] text-muted-foreground"
            >
              {pending ? "RUN" : hasFail ? "ERR" : "TOOLS"}
            </Badge>
            <span className="min-w-0 truncate font-mono text-sm text-foreground/90">
              {summaryLabel}
            </span>
            <ToolStatusBadge status={groupStatus as any} className="ml-auto" />
          </button>
        </CollapsibleTrigger>
        {pending ? <ToolStopButton onStop={() => onStop?.()} /> : null}
      </div>
      <CollapsibleContent className="flex flex-col gap-1.5 px-2.5 pb-2.5 pt-1.5">
        {tools.map((t) => (
          <ToolCard
            key={(t as any).id || t.callId || t.name}
            item={t}
            nested
            onInspect={onInspect}
            onStop={onStop}
          />
        ))}
      </CollapsibleContent>
    </Collapsible>
  );
}

export default ToolCallGroup;
