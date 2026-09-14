import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronRight } from "lucide-react";

import { ToolCard } from "@/components/chat/ToolCard";
import { ToolStatusBadge, ToolStopButton } from "@/components/tools/ToolStatusBadge";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import type { ToolCardItem } from "@/components/tools/toolRegistry";
import { shortToolName } from "@/lib/toolChip";
import { isToolPending, resolveToolStatus } from "@/lib/toolStatus";
import { cn } from "@/lib/utils";

export type ToolCallGroupProps = {
  tools: ToolCardItem[];
  highlightCallId?: string | null;
  onInspect?: (activityId: string) => void;
  onStop?: (callId?: string) => void;
  className?: string;
  /** When true (inside TurnProcessFold), skip group chrome and list chips directly. */
  flat?: boolean;
};

export function ToolCallGroup({
  tools,
  highlightCallId,
  onInspect,
  onStop,
  className,
  flat = false,
}: ToolCallGroupProps) {
  const pending = tools.some((t) => isToolPending(t));
  const hasHighlight =
    !!highlightCallId &&
    tools.some((t) => t.callId === highlightCallId || (t as any).id === highlightCallId);

  const userTouchedRef = useRef(false);
  // Live stream: open when running or highlighted; otherwise collapsed summary.
  const [open, setOpen] = useState(pending || hasHighlight || tools.length <= 2);

  const handleOpenChange = (next: boolean) => {
    userTouchedRef.current = true;
    setOpen(next);
  };

  useEffect(() => {
    if (userTouchedRef.current) return;
    if (hasHighlight || pending) setOpen(true);
  }, [hasHighlight, highlightCallId, pending]);

  const stats = useMemo(() => {
    let running = 0;
    let done = 0;
    let failed = 0;
    for (const t of tools) {
      const st = resolveToolStatus(t);
      if (st === "running") running += 1;
      else if (st === "failed") failed += 1;
      else if (st === "done" || st === "stopped") done += 1;
    }
    return { running, done, failed, total: tools.length };
  }, [tools]);

  const activeTool = useMemo(() => {
    const running = tools.find((t) => resolveToolStatus(t) === "running");
    if (running) return shortToolName(running.name);
    const last = tools[tools.length - 1];
    return shortToolName(last?.name);
  }, [tools]);

  const hasFail = stats.failed > 0;
  const groupStatus = pending ? "running" : hasFail ? "failed" : "done";

  const statusLine = useMemo(() => {
    const parts: string[] = [`${stats.total} 工具`];
    if (stats.running) parts.push(`运行 ${stats.running}`);
    if (stats.failed) parts.push(`失败 ${stats.failed}`);
    else if (!stats.running && stats.done) parts.push(`完成 ${stats.done}`);
    return parts.join(" · ");
  }, [stats]);

  const list = (
    <div className={cn("flex flex-col gap-0.5", !flat && open && "pt-0.5")}>
      {tools.map((t) => (
        <ToolCard
          key={(t as any).id || t.callId || t.name}
          item={t}
          nested
          highlighted={
            !!highlightCallId &&
            (t.callId === highlightCallId || (t as any).id === highlightCallId)
          }
          onInspect={onInspect}
          onStop={onStop}
        />
      ))}
    </div>
  );

  // Single tool or flat mode: no outer group chrome.
  if (flat || tools.length === 1) {
    return <div className={cn("w-full", className)}>{list}</div>;
  }

  return (
    <Collapsible
      open={open}
      onOpenChange={handleOpenChange}
      className={cn("tool-group w-full max-w-full self-stretch", className)}
    >
      <div className="flex items-center gap-0.5">
        <CollapsibleTrigger asChild>
          <button
            type="button"
            className={cn(
              "inline-flex min-w-0 flex-1 items-center gap-1.5 rounded-md px-1.5 py-1 text-left text-[12px] text-muted-foreground",
              "hover:bg-muted/40 hover:text-foreground",
            )}
          >
            <ChevronRight
              className={cn("size-3 shrink-0 transition-transform", open && "rotate-90")}
              aria-hidden
            />
            <span className="min-w-0 truncate font-mono text-[12px] text-foreground/85">
              {pending ? (
                <>
                  <span className="text-sky-700 dark:text-sky-300/90">调用中</span>
                  <span className="text-muted-foreground"> · </span>
                  {activeTool}
                </>
              ) : (
                <>
                  {statusLine}
                  <span className="text-muted-foreground"> · </span>
                  {activeTool}
                </>
              )}
            </span>
            <ToolStatusBadge status={groupStatus as any} className="ml-auto h-4 px-1 text-[9.5px]" />
          </button>
        </CollapsibleTrigger>
        {pending ? (
          <ToolStopButton
            onStop={() => {
              const running = tools.find((t) => isToolPending(t));
              onStop?.(running?.callId || (running as any)?.id);
            }}
          />
        ) : null}
      </div>
      <CollapsibleContent>{list}</CollapsibleContent>
    </Collapsible>
  );
}

export default ToolCallGroup;
