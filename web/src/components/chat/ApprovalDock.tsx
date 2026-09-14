import { useEffect, useMemo, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { approvalTimeoutSec } from "@/lib/approvalTimeout";
import { cn } from "@/lib/utils";

export type ApprovalDockItem = {
  id: string;
  callId: string;
  name?: string;
  base?: string;
  arguments?: Record<string, any>;
  status?: string;
};

export type ApprovalDockProps = {
  items: ApprovalDockItem[];
  onResolve: (ev: {
    item: ApprovalDockItem;
    action: "allow" | "allow_session" | "deny";
  }) => void;
  /** Fires when the focused pending approval callId changes (for tool-card highlight). */
  onActiveCallIdChange?: (callId: string | null) => void;
  className?: string;
};

function summarize(item: ApprovalDockItem) {
  const args = item.arguments || {};
  const base = item.base || item.name || "";
  if (base === "run_shell" || String(base).includes("run_shell")) return args.command || "";
  if (
    base === "write_file" ||
    base === "edit_file" ||
    String(base).includes("write_file") ||
    String(base).includes("edit_file")
  ) {
    return args.path || "";
  }
  try {
    return JSON.stringify(args).slice(0, 280);
  } catch {
    return String(args);
  }
}

function timeoutSeconds(item: ApprovalDockItem | null) {
  if (!item) return approvalTimeoutSec();
  return approvalTimeoutSec(item.base || item.name);
}

/** Floating approval panel above the composer — graduated countdown, auto-deny. */
export function ApprovalDock({ items, onResolve, onActiveCallIdChange, className }: ApprovalDockProps) {
  const pending = useMemo(
    () => items.filter((it) => it.status === "pending" || !it.status),
    [items],
  );
  const current = pending[0] || null;
  const queueLeft = Math.max(0, pending.length - 1);

  const [secondsLeft, setSecondsLeft] = useState(() => timeoutSeconds(current));
  const totalSecRef = useRef(timeoutSeconds(current));
  const resolvingRef = useRef(false);
  const callIdRef = useRef<string | null>(null);
  const onResolveRef = useRef(onResolve);
  onResolveRef.current = onResolve;
  const onActiveRef = useRef(onActiveCallIdChange);
  onActiveRef.current = onActiveCallIdChange;

  useEffect(() => {
    onActiveRef.current?.(current?.callId || null);
  }, [current?.callId]);

  useEffect(() => {
    if (!current) {
      callIdRef.current = null;
      resolvingRef.current = false;
      return;
    }
    if (callIdRef.current !== current.callId) {
      callIdRef.current = current.callId;
      resolvingRef.current = false;
      const sec = timeoutSeconds(current);
      totalSecRef.current = sec;
      setSecondsLeft(sec);
    }
  }, [current]);

  useEffect(() => {
    if (!current) return;
    const timer = window.setInterval(() => {
      setSecondsLeft((s) => {
        if (s <= 1) {
          window.clearInterval(timer);
          if (!resolvingRef.current && current) {
            resolvingRef.current = true;
            onResolveRef.current({ item: current, action: "deny" });
          }
          return 0;
        }
        return s - 1;
      });
    }, 1000);
    return () => window.clearInterval(timer);
  }, [current?.callId]);

  if (!current) return null;

  const progress = Math.max(0, Math.min(1, secondsLeft / Math.max(1, totalSecRef.current)));
  const urgent = secondsLeft <= 8;

  const act = (action: "allow" | "allow_session" | "deny") => {
    if (resolvingRef.current) return;
    resolvingRef.current = true;
    onResolve({ item: current, action });
  };

  return (
    <div
      className={cn(
        "nlm-approval-dock shrink-0 border-t border-destructive/30 bg-destructive/[0.07] px-3 py-2.5 backdrop-blur-sm",
        className,
      )}
      role="alertdialog"
      aria-label="工具审批"
    >
      <div className="mx-auto w-full max-w-[var(--chat-col-w,720px)]">
        <div className="mb-2 flex items-center gap-2 text-xs">
          <span className="font-bold tracking-wide text-destructive">审批</span>
          <span className="min-w-0 truncate font-mono text-foreground">{current.name}</span>
          {queueLeft > 0 ? (
            <span className="text-muted-foreground">· 另有 {queueLeft} 项排队</span>
          ) : null}
          <span
            className={cn(
              "ml-auto tabular-nums font-mono font-semibold",
              urgent ? "text-destructive" : "text-muted-foreground",
            )}
            aria-live="polite"
          >
            {secondsLeft}s
          </span>
        </div>

        <div className="mb-2 h-1 overflow-hidden rounded-full bg-border/60">
          <div
            className={cn(
              "h-full rounded-full transition-[width] duration-1000 ease-linear",
              urgent ? "bg-destructive" : "bg-primary/80",
            )}
            style={{ width: `${progress * 100}%` }}
          />
        </div>

        <pre className="m-0 mb-2.5 max-h-[140px] overflow-auto whitespace-pre-wrap break-words rounded-md border border-border/80 bg-background/55 px-2.5 py-2 font-mono text-[11.5px] leading-relaxed text-foreground/90">
          {summarize(current) || "（无参数预览）"}
        </pre>

        <div className="flex flex-wrap gap-1.5">
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-7 border-emerald-500/50 px-2.5 text-xs text-emerald-700 dark:text-emerald-400 hover:bg-emerald-500/10"
            onClick={() => act("allow")}
          >
            仅允许这次
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-7 border-primary/50 px-2.5 text-xs text-primary hover:bg-primary/10"
            title="开启 Accept：本会话后续写/shell 操作不再询问"
            onClick={() => act("allow_session")}
          >
            本会话自动接受
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-7 border-destructive/45 px-2.5 text-xs text-destructive hover:bg-destructive/10"
            onClick={() => act("deny")}
          >
            拒绝
          </Button>
          <span className="ml-auto self-center text-[10px] text-muted-foreground">
            超时将自动拒绝
          </span>
        </div>
      </div>
    </div>
  );
}

export type ApprovalDecision = "allowed" | "denied" | "allow_session";

const DECISION_LABEL: Record<ApprovalDecision, string> = {
  allowed: "已审批",
  denied: "已拒绝",
  allow_session: "本会话接受",
};

export function ApprovalDecisionBadge({
  decision,
  className,
}: {
  decision?: ApprovalDecision | string | null;
  className?: string;
}) {
  if (!decision) return null;
  const key = decision as ApprovalDecision;
  const label = DECISION_LABEL[key] || String(decision);
  return (
    <span
      className={cn(
        "inline-flex h-5 shrink-0 items-center rounded border px-1.5 font-mono text-[10px] font-medium tracking-wide",
        key === "allowed" && "border-emerald-500/35 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300/90",
        key === "allow_session" && "border-sky-500/35 bg-sky-500/10 text-sky-700 dark:text-sky-300/90",
        key === "denied" && "border-rose-500/35 bg-rose-500/10 text-rose-700 dark:text-rose-300/90",
        !DECISION_LABEL[key] && "border-border bg-muted/40 text-muted-foreground",
        className,
      )}
    >
      {label}
    </span>
  );
}

export default ApprovalDock;
