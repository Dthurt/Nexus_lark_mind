import { useState } from "react";
import { ChevronRight } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { pretty } from "@/lib/pretty";
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
};

export type GenericToolCardProps = {
  item: ToolCardItem;
  nested?: boolean;
  onInspect?: (activityId: string) => void;
  onOpenChange?: (open: boolean) => void;
};

function metaLabel(item: ToolCardItem): string {
  if (item.durationMs != null) {
    const n = Number(item.durationMs);
    return `${Number.isFinite(n) ? n.toFixed(1) : item.durationMs} ms`;
  }
  return item.callId || "";
}

export function GenericToolCard({
  item,
  nested = false,
  onInspect,
  onOpenChange,
}: GenericToolCardProps) {
  const [open, setOpen] = useState(!!item.open);
  const status = item.status || "";

  return (
    <Collapsible
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        onOpenChange?.(next);
      }}
      className={cn(
        "tool-card rounded-lg border border-border/80 bg-card/40 text-sm",
        nested && "ml-2 border-dashed",
        status === "ok" && "data-[state=open]:border-teal/40 data-[state=open]:bg-teal/5",
        status === "fail" &&
          "data-[state=open]:border-destructive/40 data-[state=open]:bg-destructive/5",
        status,
      )}
    >
      <CollapsibleTrigger asChild>
        <button
          type="button"
          className={cn(
            "flex w-full items-center gap-1.5 px-2 py-1.5 text-left",
            "hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
            open && !nested && "border-b border-border/60",
          )}
        >
          <ChevronRight
            className={cn(
              "size-3.5 shrink-0 text-muted-foreground transition-transform",
              open && "rotate-90",
            )}
            aria-hidden
          />
          <Badge
            variant="outline"
            className="h-5 shrink-0 px-1.5 font-mono text-[10px] font-medium text-[hsl(var(--tool))]"
          >
            {item.badge || "CALL"}
          </Badge>
          <span className="min-w-0 flex-1 truncate font-mono text-xs">{item.name}</span>
          <span className="shrink-0 font-mono text-[10px] text-muted-foreground">
            {metaLabel(item)}
          </span>
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent className="space-y-2 px-2.5 py-2">
        {item.arguments != null && (
          <div className="space-y-1">
            <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
              Arguments
            </div>
            <pre className="max-h-40 overflow-auto whitespace-pre-wrap break-words rounded-md border border-border bg-background/50 p-2 font-mono text-[10.5px] text-muted-foreground">
              {pretty(item.arguments)}
            </pre>
          </div>
        )}
        {item.error != null ? (
          <div className="space-y-1">
            <div className="text-[10px] uppercase tracking-wide text-destructive">Error</div>
            <pre className="max-h-40 overflow-auto whitespace-pre-wrap break-words rounded-md border border-destructive/30 bg-destructive/5 p-2 font-mono text-[10.5px]">
              {pretty(item.error)}
            </pre>
          </div>
        ) : item.result != null ? (
          <div className="space-y-1">
            <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
              Result
            </div>
            <pre className="max-h-40 overflow-auto whitespace-pre-wrap break-words rounded-md border border-border bg-background/50 p-2 font-mono text-[10.5px] text-muted-foreground">
              {pretty(item.result)}
            </pre>
          </div>
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
