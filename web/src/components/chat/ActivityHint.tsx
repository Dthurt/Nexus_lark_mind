import { useEffect, useMemo, useState } from "react";

import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";

export type ActivityHintProps = {
  active?: boolean;
  embedded?: boolean;
  phase?: string;
  label?: string;
  detail?: string;
  startedAt?: number;
  className?: string;
};

function phaseIconClass(phase: string) {
  switch (phase) {
    case "tool":
      return "border-t-[hsl(var(--tool))]";
    case "subagent":
      return "border-t-[#a78bfa]";
    case "stream":
      return "border-t-teal";
    case "retry":
      return "border-t-[#f0a060]";
    case "stop":
      return "border-t-destructive animate-[spin_1.1s_linear_infinite]";
    case "send":
      return "border-t-primary";
    default:
      return "border-t-primary";
  }
}

export function ActivityHint({
  active = false,
  embedded = false,
  phase = "",
  label = "",
  detail = "",
  startedAt = 0,
  className,
}: ActivityHintProps) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!active) return;
    setNow(Date.now());
    const timer = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(timer);
  }, [active]);

  const elapsedText = useMemo(() => {
    if (!active || !startedAt) return "";
    const s = Math.max(0, (now - startedAt) / 1000);
    if (s < 1) return "";
    if (s < 60) return `${s.toFixed(s < 10 ? 1 : 0)}s`;
    const m = Math.floor(s / 60);
    const rem = Math.floor(s % 60);
    return `${m}:${String(rem).padStart(2, "0")}`;
  }, [active, startedAt, now]);

  if (!active || !label) return null;

  const elapsedSec = active && startedAt ? Math.max(0, (now - startedAt) / 1000) : 0;
  const indeterminate = Math.min(92, 12 + elapsedSec * 4);

  return (
    <div
      className={cn(
        "flex min-h-7 flex-col gap-1 px-1 py-1.5 text-xs text-muted-foreground",
        embedded && "mt-0.5 min-h-[22px] px-0 py-0.5",
        className,
      )}
      role="status"
      aria-live="polite"
    >
      <div className="flex items-center gap-2">
        <span
          className={cn(
            "size-3 shrink-0 animate-spin rounded-full border-[1.5px] border-muted-foreground/25",
            phaseIconClass(phase),
          )}
          aria-hidden
        />
        <span className="inline-flex min-w-0 flex-1 items-baseline gap-1.5">
          <span className="whitespace-nowrap text-foreground/85">{label}</span>
          {detail ? (
            <span className="min-w-0 truncate font-mono text-[10px] text-muted-foreground">
              {detail}
            </span>
          ) : null}
        </span>
        {elapsedText ? (
          <span
            className="shrink-0 font-mono text-[10px] tracking-wide text-muted-foreground/85"
            title={`已进行 ${elapsedText}`}
          >
            {elapsedText}
          </span>
        ) : null}
      </div>
      <Progress value={indeterminate} className="h-0.5" />
    </div>
  );
}

export default ActivityHint;
