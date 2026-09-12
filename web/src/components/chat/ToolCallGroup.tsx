import { useEffect, useMemo, useState } from "react";
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
  const pending = tools.some((t) => isToolPending(t));
  const [open, setOpen] = useState(pending);

  useEffect(() => {
    if (pending) setOpen(true);
  }, [pending]);

  const stats = useMemo(() => {
    let running = 0;
    let done = 0;
    let failed = 0;
    let accepted = 0;
    let denied = 0;
    for (const t of tools) {
      const st = resolveToolStatus(t);
      if (st === "running") running += 1;
      else if (st === "failed") failed += 1;
      else if (st === "done" || st === "stopped") done += 1;
      const d = String((t as any).approvalDecision || "").toLowerCase();
      if (d === "allowed" || d === "allow_session") accepted += 1;
      if (d === "denied") denied += 1;
    }
    return { running, done, failed, accepted, denied, total: tools.length };
  }, [tools]);

  const activeTool = useMemo(() => {
    const running = tools.find((t) => resolveToolStatus(t) === "running");
    if (running) return shortName(running.name);
    const last = tools[tools.length - 1];
    return shortName(last?.name);
  }, [tools]);

  const hasFail = stats.failed > 0;
  const groupStatus = pending ? "running" : hasFail ? "failed" : "done";

  const chips = useMemo(() => {
    const out: { key: string; label: string; className: string }[] = [];
    if (stats.running) {
      out.push({
        key: "run",
        label: `运行中 ${stats.running}`,
        className: "border-sky-500/30 bg-sky-500/10 text-sky-300/90",
      });
    }
    if (stats.accepted) {
      out.push({
        key: "ok",
        label: `已接受 ${stats.accepted}`,
        className: "border-emerald-500/30 bg-emerald-500/10 text-emerald-300/90",
      });
    }
    if (stats.denied) {
      out.push({
        key: "deny",
        label: `已拒绝 ${stats.denied}`,
        className: "border-rose-500/30 bg-rose-500/10 text-rose-300/90",
      });
    }
    if (stats.failed) {
      out.push({
        key: "fail",
        label: `失败 ${stats.failed}`,
        className: "border-rose-500/30 bg-rose-500/10 text-rose-300/90",
      });
    }
    if (!stats.running && stats.done && !stats.failed) {
      out.push({
        key: "done",
        label: `已完成 ${stats.done}`,
        className: "border-emerald-600/25 bg-emerald-600/10 text-emerald-300/85",
      });
    }
    return out;
  }, [stats]);

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
              className="h-5 shrink-0 border-border/60 bg-background/30 px-1.5 font-mono text-[10px] text-muted-foreground"
            >
              {stats.total} 工具
            </Badge>
            <span className="min-w-0 truncate font-mono text-sm text-foreground/90" title={activeTool}>
              {pending ? (
                <>
                  <span className="text-sky-300/90">调用中</span>
                  <span className="text-muted-foreground"> · </span>
                  {activeTool}
                </>
              ) : (
                activeTool
              )}
            </span>
            <span className="ml-auto flex shrink-0 items-center gap-1">
              {chips.map((c) => (
                <span
                  key={c.key}
                  className={cn(
                    "hidden h-5 items-center rounded border px-1.5 font-mono text-[10px] sm:inline-flex",
                    c.className,
                  )}
                >
                  {c.label}
                </span>
              ))}
              <ToolStatusBadge status={groupStatus as any} />
            </span>
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
