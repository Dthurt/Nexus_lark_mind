import { Square } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  STATUS_LABEL,
  statusChipClass,
  type ToolRunStatus,
} from "@/lib/toolStatus";
import { cn } from "@/lib/utils";

export type ToolStatusBadgeProps = {
  status: ToolRunStatus;
  className?: string;
};

export function ToolStatusBadge({ status, className }: ToolStatusBadgeProps) {
  return (
    <Badge
      variant="outline"
      className={cn(
        "h-5 shrink-0 border px-1.5 font-mono text-[10px] font-medium tracking-wide",
        statusChipClass(status),
        status === "running" && "animate-pulse",
        className,
      )}
    >
      {STATUS_LABEL[status]}
    </Badge>
  );
}

export type ToolStopButtonProps = {
  onStop?: () => void;
  disabled?: boolean;
  className?: string;
};

/** Tiny stop control for a running tool / subagent. */
export function ToolStopButton({ onStop, disabled, className }: ToolStopButtonProps) {
  if (!onStop) return null;
  return (
    <Button
      type="button"
      variant="outline"
      size="icon"
      className={cn(
        "size-6 shrink-0 rounded-md border-border/80 text-muted-foreground hover:border-rose-500/35 hover:bg-rose-500/10 hover:text-rose-300",
        className,
      )}
      title="Stop"
      aria-label="Stop tool"
      disabled={disabled}
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        onStop();
      }}
    >
      <Square className="size-2.5 fill-current" />
    </Button>
  );
}
