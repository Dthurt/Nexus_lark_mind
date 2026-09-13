import { useEffect, useState } from "react";

import { ToolChipShell } from "@/components/tools/ToolChipShell";
import { pretty } from "@/lib/pretty";
import { oneLinePreview, shortToolName } from "@/lib/toolChip";
import { resolveToolStatus } from "@/lib/toolStatus";
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
  highlighted?: boolean;
  onInspect?: (activityId: string) => void;
  onOpenChange?: (open: boolean) => void;
  onStop?: (callId?: string) => void;
};

function PreBlock({
  children,
  tone = "default",
}: {
  children: string;
  tone?: "default" | "error";
}) {
  return (
    <pre
      className={cn(
        "max-h-40 overflow-auto whitespace-pre-wrap break-words rounded-md p-2 font-mono text-[10.5px]",
        tone === "error"
          ? "border border-rose-500/25 bg-rose-500/[0.04] text-rose-100/90"
          : "border border-border/50 bg-background/35 text-muted-foreground",
      )}
    >
      {children}
    </pre>
  );
}

export function GenericToolCard({
  item,
  nested = false,
  highlighted = false,
  onInspect,
  onOpenChange,
  onStop,
}: GenericToolCardProps) {
  const runStatus = resolveToolStatus(item);
  const pending = runStatus === "running";
  const title = shortToolName(item.name);
  const [open, setOpen] = useState(!!item.open);

  useEffect(() => {
    if (item.open) setOpen(true);
  }, [item.open]);

  const summary =
    item.error != null
      ? oneLinePreview(item.error, 80)
      : pending
        ? "…"
        : item.result != null
          ? oneLinePreview(item.result, 80)
          : "";

  return (
    <ToolChipShell
      callId={item.callId}
      status={runStatus}
      badge={item.badge || "CALL"}
      title={title}
      summary={summary}
      durationMs={item.durationMs}
      nested={nested}
      highlighted={highlighted}
      defaultOpen={open || !!item.open}
      onOpenChange={(next) => {
        setOpen(next);
        onOpenChange?.(next);
      }}
      onStop={() => onStop?.(item.callId)}
      fullName={item.name}
      openaiName={item.openaiName}
      approvalDecision={item.approvalDecision}
      activityId={item.activityId}
      onInspect={onInspect}
    >
      {item.arguments != null ? (
        <div className="space-y-0.5">
          <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Arguments</div>
          <PreBlock>{pretty(item.arguments)}</PreBlock>
        </div>
      ) : null}
      {item.error != null ? (
        <div className="space-y-0.5">
          <div className="text-[10px] uppercase tracking-wide text-rose-300/80">Error</div>
          <PreBlock tone="error">{pretty(item.error)}</PreBlock>
        </div>
      ) : item.result != null ? (
        <div className="space-y-0.5">
          <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Result</div>
          <PreBlock>{pretty(item.result)}</PreBlock>
        </div>
      ) : pending ? (
        <p className="m-0 text-[11px] text-muted-foreground">等待结果…</p>
      ) : null}
    </ToolChipShell>
  );
}

export default GenericToolCard;
