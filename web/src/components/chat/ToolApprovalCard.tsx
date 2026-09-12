import { useMemo } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export type ToolApprovalItem = {
  name?: string;
  base?: string;
  arguments?: Record<string, any>;
  status?: string;
};

export type ToolApprovalCardProps = {
  item: ToolApprovalItem;
  onResolve?: (ev: { action: "allow" | "allow_session" | "deny" }) => void;
  className?: string;
};

export function ToolApprovalCard({ item, onResolve, className }: ToolApprovalCardProps) {
  const args = item.arguments || {};
  const base = item.base || item.name || "";
  const pending = item.status === "pending";

  const summary = useMemo(() => {
    if (base === "run_shell") return args.command || "";
    if (base === "write_file" || base === "edit_file") return args.path || "";
    try {
      return JSON.stringify(args).slice(0, 200);
    } catch {
      return String(args);
    }
  }, [args, base]);

  const stateLabel =
    item.status === "allowed" ? "已允许" : item.status === "denied" ? "已拒绝" : item.status;

  return (
    <div
      className={cn(
        "grid max-w-[min(100%,720px)] gap-2 rounded-[10px] border border-destructive/35 bg-destructive/10 px-3 py-2.5",
        item.status === "allowed" && "border-emerald-500/40 bg-emerald-500/10",
        item.status === "denied" && "opacity-75",
        className,
      )}
    >
      <div className="flex items-center gap-2 text-xs">
        <span className="font-bold tracking-wide text-[#f85149]">审批</span>
        <span className="font-mono text-foreground">{item.name}</span>
        {!pending ? <span className="ml-auto text-muted-foreground">{stateLabel}</span> : null}
      </div>
      <pre className="m-0 max-h-[180px] overflow-auto whitespace-pre-wrap break-words rounded-md border border-border bg-black/35 px-2.5 py-2 font-mono text-xs">
        {summary}
      </pre>
      {pending ? (
        <div className="flex flex-wrap gap-1.5">
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-7 border-emerald-500/50 px-2.5 text-xs text-emerald-400"
            onClick={() => onResolve?.({ action: "allow" })}
          >
            仅允许这次
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-7 border-primary/50 px-2.5 text-xs text-primary"
            onClick={() => onResolve?.({ action: "allow_session" })}
          >
            本会话自动接受
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-7 border-destructive/45 px-2.5 text-xs text-destructive"
            onClick={() => onResolve?.({ action: "deny" })}
          >
            拒绝
          </Button>
        </div>
      ) : null}
    </div>
  );
}

export default ToolApprovalCard;
