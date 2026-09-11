import { useMemo, useState } from "react";
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
};

export type SubagentCardProps = {
  item: SubagentItem;
  onInspect?: (activityId: string) => void;
  onOpenChange?: (open: boolean) => void;
  className?: string;
};

export function SubagentCard({ item, onInspect, onOpenChange, className }: SubagentCardProps) {
  const [open, setOpen] = useState(!!item.open);

  const statusLabel = useMemo(() => {
    if (item.error) return "失败";
    if (item.status === "running") return "运行中";
    if (item.status === "interrupted") return "已中断";
    if (item.status === "idle" || item.output) return "完成";
    return item.status || "subagent";
  }, [item.error, item.status, item.output]);

  const summary = useMemo(() => {
    return [item.label || item.name || "subagent", item.mode ? String(item.mode) : null, statusLabel]
      .filter(Boolean)
      .join(" · ");
  }, [item.label, item.name, item.mode, statusLabel]);

  const nestedTools = item.childTools || [];
  const tone =
    item.status || (item.error ? "fail" : item.output ? "ok" : "running");

  return (
    <Collapsible
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        item.open = next;
        onOpenChange?.(next);
      }}
      className={cn(
        "subagent-card w-fit max-w-[min(100%,560px)] self-start animate-in fade-in duration-150",
        open && "w-[min(100%,560px)] rounded-lg border border-violet-400/35 bg-violet-400/10",
        className,
      )}
    >
      <CollapsibleTrigger asChild>
        <button
          type="button"
          className={cn(
            "inline-flex items-center gap-1.5 rounded-full border border-violet-400/35 bg-violet-400/10 px-2.5 py-1 text-sm font-medium text-violet-300",
            "hover:border-violet-400/55 hover:text-violet-100",
            open && "flex w-full rounded-none border-0 bg-transparent text-violet-100",
            tone === "running" && "border-violet-400/55",
            tone === "fail" && "border-destructive/45 text-[#f0a0a0]",
          )}
        >
          <ChevronRight
            className={cn("size-3.5 shrink-0 transition-transform", open && "rotate-90")}
            aria-hidden
          />
          <Badge
            variant="outline"
            className="h-5 border-0 bg-violet-400/20 px-1.5 font-mono text-[10px] text-violet-300"
          >
            SUB
          </Badge>
          <span className="min-w-0 truncate font-mono text-sm">{summary}</span>
          {item.subagentId ? (
            <span className="ml-auto shrink-0 font-mono text-[10px] text-violet-300/70">
              {item.subagentId}
            </span>
          ) : null}
        </button>
      </CollapsibleTrigger>

      <CollapsibleContent className="grid gap-2 px-2.5 pb-2.5 pt-0.5">
        {item.prompt ? (
          <div>
            <div className="mb-1 text-[10px] uppercase tracking-wide text-violet-300/75">Input</div>
            <pre className="m-0 max-h-[220px] overflow-auto whitespace-pre-wrap break-words rounded-md border border-violet-400/20 bg-black/30 p-2 font-mono text-xs">
              {item.prompt}
            </pre>
          </div>
        ) : null}
        {item.streamText ? (
          <div>
            <div className="mb-1 text-[10px] uppercase tracking-wide text-violet-300/75">
              Output{item.status === "running" ? " (streaming)" : ""}
            </div>
            <pre className="m-0 max-h-[220px] overflow-auto whitespace-pre-wrap break-words rounded-md border border-violet-400/20 bg-black/30 p-2 font-mono text-xs">
              {item.streamText}
            </pre>
          </div>
        ) : null}
        {nestedTools.length ? (
          <div>
            <div className="mb-1 text-[10px] uppercase tracking-wide text-violet-300/75">
              Child tools
            </div>
            <div className="flex flex-col gap-1">
              {nestedTools.map((t, i) => (
                <div
                  key={t.id || i}
                  className={cn(
                    "flex justify-between gap-2 rounded-md border border-violet-400/15 px-2 py-1 font-mono text-[10px] text-muted-foreground",
                    t.status === "ok" && "border-teal/30",
                    t.status === "fail" && "border-destructive/35",
                  )}
                >
                  <span>{t.name}</span>
                  <span>
                    {t.success === false ? "fail" : t.success ? "ok" : "…"}
                  </span>
                </div>
              ))}
            </div>
          </div>
        ) : null}
        {item.error ? (
          <div>
            <div className="mb-1 text-[10px] uppercase tracking-wide text-violet-300/75">Error</div>
            <pre className="m-0 max-h-[220px] overflow-auto whitespace-pre-wrap break-words rounded-md border border-violet-400/20 bg-black/30 p-2 font-mono text-xs">
              {pretty(item.error)}
            </pre>
          </div>
        ) : item.output && item.output !== item.streamText ? (
          <div>
            <div className="mb-1 text-[10px] uppercase tracking-wide text-violet-300/75">Final</div>
            <pre className="m-0 max-h-[220px] overflow-auto whitespace-pre-wrap break-words rounded-md border border-violet-400/20 bg-black/30 p-2 font-mono text-xs">
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
              className="h-6 border-violet-400/30 px-2 text-[10.5px] text-violet-300"
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
