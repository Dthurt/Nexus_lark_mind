/** Shared tool / subagent run-status helpers — low-sat premium tones. */

export type ToolRunStatus = "running" | "done" | "failed" | "stopped" | "idle";

export function resolveToolStatus(item: {
  status?: string | null;
  error?: unknown;
  success?: boolean | null;
  result?: unknown;
  output?: unknown;
}): ToolRunStatus {
  const s = String(item.status || "").toLowerCase();
  if (item.error != null || item.success === false || s === "fail" || s === "failed") {
    return "failed";
  }
  if (s === "stopped" || s === "interrupted" || s === "cancelled") return "stopped";
  if (s === "ok" || s === "done" || s === "idle" || item.success === true) return "done";
  if (item.result != null || item.output) return "done";
  if (s === "running" || s === "") return "running";
  return "idle";
}

export const STATUS_LABEL: Record<ToolRunStatus, string> = {
  running: "Running",
  done: "Done",
  failed: "Failed",
  stopped: "Stopped",
  idle: "Idle",
};

/** Outer shell — muted borders, never neon. */
export function statusShellClass(status: ToolRunStatus) {
  switch (status) {
    case "running":
      return "border-sky-500/30 bg-sky-500/[0.045]";
    case "done":
      return "border-emerald-600/25 bg-emerald-600/[0.035]";
    case "failed":
      return "border-rose-500/30 bg-rose-500/[0.04]";
    case "stopped":
      return "border-amber-600/25 bg-amber-600/[0.035]";
    default:
      return "border-border/70 bg-card/35";
  }
}

export function statusChipClass(status: ToolRunStatus) {
  switch (status) {
    case "running":
      return "border-sky-500/25 bg-sky-500/10 text-sky-300/90";
    case "done":
      return "border-emerald-600/25 bg-emerald-600/10 text-emerald-300/85";
    case "failed":
      return "border-rose-500/25 bg-rose-500/10 text-rose-300/90";
    case "stopped":
      return "border-amber-600/25 bg-amber-600/10 text-amber-200/85";
    default:
      return "border-border bg-muted/40 text-muted-foreground";
  }
}

export function statusAccentBar(status: ToolRunStatus) {
  switch (status) {
    case "running":
      return "bg-sky-500/55";
    case "done":
      return "bg-emerald-600/45";
    case "failed":
      return "bg-rose-500/50";
    case "stopped":
      return "bg-amber-600/45";
    default:
      return "bg-foreground/15";
  }
}

export function isToolPending(item: {
  status?: string | null;
  error?: unknown;
  success?: boolean | null;
  result?: unknown;
}) {
  return resolveToolStatus(item) === "running";
}
