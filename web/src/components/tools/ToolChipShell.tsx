import { useEffect, useRef, useState, type ReactNode } from "react";
import { ChevronRight } from "lucide-react";

import { ApprovalDecisionBadge } from "@/components/chat/ApprovalDock";
import { ToolStatusBadge, ToolStopButton } from "@/components/tools/ToolStatusBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { formatToolDurationMs, shouldAutoExpandTool } from "@/lib/toolChip";
import {
  statusAccentBar,
  statusShellClass,
  type ToolRunStatus,
} from "@/lib/toolStatus";
import { cn } from "@/lib/utils";

export type ToolChipShellProps = {
  callId?: string;
  status: ToolRunStatus;
  /** Short badge e.g. SHELL / GREP / CALL */
  badge?: string;
  /** Primary title — prefer short tool key */
  title: string;
  /** One-line collapsed summary */
  summary?: string;
  durationMs?: number | null;
  /** Extra collapsed header bits (e.g. ±stats) */
  headerExtra?: ReactNode;
  nested?: boolean;
  highlighted?: boolean;
  /** Force initial/controlled open from parent item.open */
  defaultOpen?: boolean;
  onOpenChange?: (open: boolean) => void;
  onStop?: () => void;
  /** Full tool id / openai name shown only when expanded */
  fullName?: string;
  openaiName?: string;
  approvalDecision?: string | null;
  activityId?: string;
  onInspect?: (activityId: string) => void;
  /** Collapsed one-line preview under the header (optional) */
  collapsedPreview?: string;
  children?: ReactNode;
  className?: string;
};

export function ToolChipShell({
  callId,
  status,
  badge,
  title,
  summary = "",
  durationMs,
  headerExtra,
  nested = false,
  highlighted = false,
  defaultOpen = false,
  onOpenChange,
  onStop,
  fullName,
  openaiName,
  approvalDecision,
  activityId,
  onInspect,
  collapsedPreview,
  children,
  className,
}: ToolChipShellProps) {
  const pending = status === "running";
  const duration = formatToolDurationMs(durationMs);
  const userTouchedRef = useRef(false);
  const [open, setOpen] = useState(() =>
    shouldAutoExpandTool({ status, highlighted, forcedOpen: defaultOpen }),
  );

  useEffect(() => {
    if (userTouchedRef.current) return;
    if (shouldAutoExpandTool({ status, highlighted, forcedOpen: defaultOpen })) {
      setOpen(true);
    }
  }, [status, highlighted, defaultOpen]);

  const setOpenBoth = (next: boolean) => {
    userTouchedRef.current = true;
    setOpen(next);
    onOpenChange?.(next);
  };

  return (
    <Collapsible
      open={open}
      onOpenChange={setOpenBoth}
      className={cn(
        "tool-chip group/chip relative w-full max-w-full self-stretch overflow-hidden text-sm transition-colors",
        nested
          ? "rounded-md border-0 bg-transparent hover:bg-foreground/[0.03]"
          : cn("rounded-md border", statusShellClass(status)),
        highlighted && "ring-2 ring-amber-400/70 border-amber-400/50",
        className,
      )}
      data-approval-call={callId || undefined}
    >
      {!nested ? (
        <div className={cn("absolute inset-y-0 left-0 w-0.5", statusAccentBar(status))} aria-hidden />
      ) : (
        <span
          className={cn(
            "absolute left-1.5 top-1/2 size-1.5 -translate-y-1/2 rounded-full",
            statusAccentBar(status),
            pending && "animate-pulse",
          )}
          aria-hidden
        />
      )}
      <div className={cn("flex items-center gap-0.5 pr-1", nested && "pl-3.5")}>
        <CollapsibleTrigger asChild>
          <button
            type="button"
            className={cn(
              "flex min-w-0 flex-1 items-center gap-1.5 py-1 text-left",
              nested ? "pl-1" : "pl-2.5",
              "hover:bg-foreground/[0.03] focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
              open && !nested && "border-b border-border/30",
            )}
          >
            <ChevronRight
              className={cn(
                "size-3 shrink-0 text-muted-foreground/70 transition-transform",
                open && "rotate-90",
              )}
              aria-hidden
            />
            {badge ? (
              <Badge
                variant="outline"
                className="h-4 shrink-0 border-border/50 bg-background/20 px-1 font-mono text-[9.5px] font-medium uppercase tracking-wide text-muted-foreground"
              >
                {badge}
              </Badge>
            ) : null}
            <span className="min-w-0 shrink-0 truncate font-mono text-[12px] font-medium text-foreground/90">
              {title}
            </span>
            {summary ? (
              <span className="min-w-0 flex-1 truncate font-mono text-[11px] text-muted-foreground">
                {summary}
              </span>
            ) : (
              <span className="min-w-0 flex-1" />
            )}
            {headerExtra}
            {!open && collapsedPreview ? (
              <span className="hidden max-w-[28%] truncate font-mono text-[10px] text-muted-foreground/70 sm:inline">
                {collapsedPreview}
              </span>
            ) : null}
            <ToolStatusBadge status={status} className="h-4 px-1 text-[9.5px]" />
            {duration ? (
              <span className="hidden shrink-0 font-mono text-[10px] tabular-nums text-muted-foreground/75 sm:inline">
                {duration}
              </span>
            ) : null}
          </button>
        </CollapsibleTrigger>
        {pending ? <ToolStopButton onStop={onStop} /> : null}
      </div>
      <CollapsibleContent className={cn("space-y-1.5 px-2.5 pb-2 pt-1", nested && "pl-5")}>
        {(fullName || openaiName || approvalDecision || (activityId && onInspect)) && (
          <div className="flex flex-wrap items-center gap-1.5 text-[10px] text-muted-foreground">
            {fullName && fullName !== title ? (
              <span className="font-mono">{fullName}</span>
            ) : null}
            {openaiName ? <span className="font-mono opacity-80">· {openaiName}</span> : null}
            <ApprovalDecisionBadge decision={approvalDecision} />
            {activityId && onInspect ? (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="ml-auto h-5 px-1.5 text-[10px]"
                onClick={(e) => {
                  e.stopPropagation();
                  onInspect(activityId);
                }}
              >
                查看活动
              </Button>
            ) : null}
          </div>
        )}
        {children}
      </CollapsibleContent>
    </Collapsible>
  );
}
