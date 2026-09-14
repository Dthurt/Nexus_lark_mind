import { useMemo, useState } from "react";
import { ChevronRight } from "lucide-react";

import { ToolStatusBadge, ToolStopButton } from "@/components/tools/ToolStatusBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Progress } from "@/components/ui/progress";
import { pretty } from "@/lib/pretty";
import {
  resolveToolStatus,
  statusAccentBar,
  statusShellClass,
  type ToolRunStatus,
} from "@/lib/toolStatus";
import { cn } from "@/lib/utils";

export type SubagentChildTool = {
  id?: string;
  name?: string;
  success?: boolean | null;
  status?: string;
};

export type SubagentItem = {
  open?: boolean;
  error?: unknown;
  status?: string;
  output?: string;
  label?: string;
  name?: string;
  mode?: string;
  subagentId?: string;
  prompt?: string;
  streamText?: string;
  childTools?: SubagentChildTool[];
  activityId?: string;
  callId?: string;
};

export type SubagentCardProps = {
  item: SubagentItem;
  onInspect?: (activityId: string) => void;
  onOpenChange?: (open: boolean) => void;
  onStop?: (callId?: string) => void;
  className?: string;
};

function childStatus(t: SubagentChildTool): ToolRunStatus {
  if (t.success === false || t.status === "fail") return "failed";
  if (t.success === true || t.status === "ok") return "done";
  return "running";
}

export function SubagentCard({
  item,
  onInspect,
  onOpenChange,
  onStop,
  className,
}: SubagentCardProps) {
  const [open, setOpen] = useState(!!item.open);

  const runStatus = useMemo(() => {
    if (item.error) return "failed" as const;
    if (item.status === "interrupted" || item.status === "stopped") return "stopped" as const;
    if (item.status === "running") return "running" as const;
    if (item.status === "idle" || item.output || item.status === "ok") return "done" as const;
    return resolveToolStatus(item);
  }, [item]);

  const summary = useMemo(() => {
    return [item.label || item.name || "subagent", item.mode ? String(item.mode) : null]
      .filter(Boolean)
      .join(" · ");
  }, [item.label, item.name, item.mode]);

  const nestedTools = item.childTools || [];
  const pending = runStatus === "running";

  return (
    <Collapsible
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        item.open = next;
        onOpenChange?.(next);
      }}
      className={cn(
        "subagent-card relative w-full max-w-full self-stretch overflow-hidden rounded-lg border transition-colors",
        statusShellClass(runStatus),
        className,
      )}
    >
      <div className={cn("absolute inset-y-0 left-0 w-0.5", statusAccentBar(runStatus))} aria-hidden />
      <div className="flex items-center gap-1 pr-1.5">
        <CollapsibleTrigger asChild>
          <button
            type="button"
            className={cn(
              "inline-flex min-w-0 flex-1 items-center gap-1.5 px-2.5 py-1.5 text-left text-sm font-medium",
              "hover:bg-foreground/[0.03]",
              open && "border-b border-border/40",
            )}
          >
            <ChevronRight
              className={cn("size-3.5 shrink-0 text-muted-foreground transition-transform", open && "rotate-90")}
              aria-hidden
            />
            <Badge
              variant="outline"
              className="h-5 border-border/60 bg-background/30 px-1.5 font-mono text-[10px] text-muted-foreground"
            >
              SUB
            </Badge>
            <span className="min-w-0 truncate font-mono text-sm text-foreground/90">{summary}</span>
            <ToolStatusBadge status={runStatus} />
          </button>
        </CollapsibleTrigger>
        {pending ? <ToolStopButton onStop={() => onStop?.(item.callId || item.subagentId)} /> : null}
      </div>

      <CollapsibleContent className="grid gap-2 px-2.5 pb-2.5 pt-1.5">
        {pending ? <Progress value={58} className="h-0.5 opacity-70" /> : null}
        {item.prompt ? (
          <div>
            <div className="mb-1 text-[10px] uppercase tracking-wide text-muted-foreground">Input</div>
            <pre className="m-0 max-h-[220px] overflow-auto whitespace-pre-wrap break-words rounded-md border border-border/50 bg-background/35 p-2 font-mono text-xs">
              {item.prompt}
            </pre>
          </div>
        ) : null}
        {item.streamText ? (
          <div>
            <div className="mb-1 text-[10px] uppercase tracking-wide text-muted-foreground">
              Output{pending ? " (streaming)" : ""}
            </div>
            <pre className="m-0 max-h-[220px] overflow-auto whitespace-pre-wrap break-words rounded-md border border-border/50 bg-background/35 p-2 font-mono text-xs">
              {item.streamText}
            </pre>
          </div>
        ) : null}
        {nestedTools.length ? (
          <div>
            <div className="mb-1 text-[10px] uppercase tracking-wide text-muted-foreground">
              Child tools
            </div>
            <div className="flex flex-col gap-1">
              {nestedTools.map((t, i) => {
                const st = childStatus(t);
                return (
                  <div
                    key={t.id || i}
                    className={cn(
                      "flex items-center justify-between gap-2 rounded-md border px-2 py-1 font-mono text-[10px]",
                      statusShellClass(st),
                    )}
                  >
                    <span className="min-w-0 truncate text-foreground/85">{t.name}</span>
                    <ToolStatusBadge status={st} />
                  </div>
                );
              })}
            </div>
          </div>
        ) : null}
        {item.error ? (
          <div>
            <div className="mb-1 text-[10px] uppercase tracking-wide text-rose-700 dark:text-rose-300/80">Error</div>
            <pre className="m-0 max-h-[220px] overflow-auto whitespace-pre-wrap break-words rounded-md border border-rose-500/25 bg-rose-500/[0.04] p-2 font-mono text-xs">
              {pretty(item.error)}
            </pre>
          </div>
        ) : item.output && item.output !== item.streamText ? (
          <div>
            <div className="mb-1 text-[10px] uppercase tracking-wide text-muted-foreground">Final</div>
            <pre className="m-0 max-h-[220px] overflow-auto whitespace-pre-wrap break-words rounded-md border border-border/50 bg-background/35 p-2 font-mono text-xs">
              {item.output}
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

export default SubagentCard;
