import { useState } from "react";
import { ChevronRight } from "lucide-react";

import { ToolStatusBadge, ToolStopButton } from "@/components/tools/ToolStatusBadge";
import { ApprovalDecisionBadge } from "@/components/chat/ApprovalDock";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { pretty } from "@/lib/pretty";
import { resolveToolStatus, statusAccentBar, statusShellClass } from "@/lib/toolStatus";
import { cn } from "@/lib/utils";

export type ToolCardItem = {
  name: string;
  badge?: string;
  status?: string;
  open?: boolean;
  arguments?: unknown;
  result?: unknown;
  error?: unknown;
  callId?: string;
  activityId?: string;
  durationMs?: number | null;
  openaiName?: string;
  approvalDecision?: string | null;
};

export type GenericToolCardProps = {
  item: ToolCardItem;
  nested?: boolean;
  onInspect?: (activityId: string) => void;
  onOpenChange?: (open: boolean) => void;
  onStop?: (callId?: string) => void;
};

function metaLabel(item: ToolCardItem): string {
  if (item.durationMs != null) {
    const n = Number(item.durationMs);
    return `${Number.isFinite(n) ? n.toFixed(1) : item.durationMs} ms`;
  }
  return "";
}

export function GenericToolCard({
  item,
  nested = false,
  onInspect,
  onOpenChange,
  onStop,
}: GenericToolCardProps) {
  const [open, setOpen] = useState(!!item.open);
  const runStatus = resolveToolStatus(item);
  const pending = runStatus === "running";
  const meta = metaLabel(item);

  return (
    <Collapsible
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        onOpenChange?.(next);
      }}
      className={cn(
        "tool-card relative w-full max-w-full self-stretch overflow-hidden rounded-lg border text-sm transition-colors",
        statusShellClass(runStatus),
        nested && "ml-0",
      )}
    >
      <div className={cn("absolute inset-y-0 left-0 w-0.5", statusAccentBar(runStatus))} aria-hidden />
      <div className="flex items-center gap-1 pr-1.5">
        <CollapsibleTrigger asChild>
          <button
            type="button"
            className={cn(
              "flex min-w-0 flex-1 items-center gap-1.5 py-1.5 pl-2.5 text-left",
              "hover:bg-foreground/[0.03] focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
              open && "border-b border-border/40",
            )}
          >
            <ChevronRight
              className={cn(
                "size-3.5 shrink-0 text-muted-foreground/80 transition-transform",
                open && "rotate-90",
              )}
              aria-hidden
            />
            <Badge
              variant="outline"
              className="h-5 shrink-0 border-border/60 bg-background/30 px-1.5 font-mono text-[10px] font-medium text-muted-foreground"
            >
              {item.badge || "CALL"}
            </Badge>
            <span className="min-w-0 flex-1 truncate font-mono text-xs text-foreground/90">
              {item.name}
            </span>
            <ToolStatusBadge status={runStatus} />
            <ApprovalDecisionBadge decision={item.approvalDecision} />
            {meta ? (
              <span className="hidden shrink-0 font-mono text-[10px] text-muted-foreground/80 sm:inline">
                {meta}
              </span>
            ) : null}
          </button>
        </CollapsibleTrigger>
        {pending ? (
          <ToolStopButton onStop={() => onStop?.(item.callId)} />
        ) : null}
      </div>
      <CollapsibleContent className="space-y-2 px-2.5 py-2">
        {item.arguments != null && (
          <div className="space-y-1">
            <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
              Arguments
            </div>
            <pre className="max-h-40 overflow-auto whitespace-pre-wrap break-words rounded-md border border-border/60 bg-background/40 p-2 font-mono text-[10.5px] text-muted-foreground">
              {pretty(item.arguments)}
            </pre>
          </div>
        )}
        {item.error != null ? (
          <div className="space-y-1">
            <div className="text-[10px] uppercase tracking-wide text-rose-300/80">Error</div>
            <pre className="max-h-40 overflow-auto whitespace-pre-wrap break-words rounded-md border border-rose-500/25 bg-rose-500/[0.04] p-2 font-mono text-[10.5px]">
              {pretty(item.error)}
            </pre>
          </div>
        ) : item.result != null ? (
          <div className="space-y-1">
            <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
              Result
            </div>
            <pre className="max-h-40 overflow-auto whitespace-pre-wrap break-words rounded-md border border-border/60 bg-background/40 p-2 font-mono text-[10.5px] text-muted-foreground">
              {pretty(item.result)}
            </pre>
          </div>
        ) : pending ? (
          <p className="m-0 text-[11px] text-muted-foreground">等待结果…</p>
        ) : null}
        {item.activityId && onInspect ? (
          <div className="flex justify-end">
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-6 px-2 text-[10.5px]"
              onClick={(e) => {
                e.stopPropagation();
                onInspect(item.activityId!);
              }}
            >
              查看活动
            </Button>
          </div>
        ) : null}
      </CollapsibleContent>
    </Collapsible>
  );
}

export default GenericToolCard;
