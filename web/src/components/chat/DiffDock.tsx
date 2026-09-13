import { Check, RotateCcw, X } from "lucide-react";

import { FileDiffBlock } from "@/components/tools/FileDiffBlock";
import { Button } from "@/components/ui/button";
import type { DiffReviewItem } from "@/hooks/useDiffReview";
import { cn } from "@/lib/utils";

export type DiffDockProps = {
  items: DiffReviewItem[];
  cwd?: string;
  workspaceKind?: string;
  onAccept: (id: string) => void;
  onReject: (id: string) => void;
  onDismiss: (id: string) => void;
  className?: string;
};

/** Post-apply file mutation review — Accept keeps, Reject reverts disk. */
export function DiffDock({
  items,
  cwd = "",
  workspaceKind = "local",
  onAccept,
  onReject,
  onDismiss,
  className,
}: DiffDockProps) {
  const pending = items.filter((i) => i.status === "pending");
  if (!pending.length) return null;

  const current = pending[0];
  const queueLeft = pending.length - 1;
  const canRevert =
    workspaceKind === "local" &&
    !!cwd &&
    (current.kind === "edit" ||
      current.created ||
      (current.previous != null && !current.previousOmitted));

  return (
    <div
      className={cn(
        "nlm-diff-dock mx-auto w-full max-w-[var(--chat-col-w,720px)] shrink-0 px-1 pb-1",
        className,
      )}
      aria-label="变更审阅"
    >
      <div className="rounded-lg border border-teal/35 bg-card/90 px-2.5 py-2 shadow-sm backdrop-blur-sm">
        <div className="mb-1.5 flex flex-wrap items-center gap-2">
          <span className="text-[11px] font-medium text-foreground">变更审阅</span>
          <span className="font-mono text-[10px] text-muted-foreground">
            {current.kind === "write" ? (current.created ? "新建" : "覆写") : "编辑"} · {current.path}
          </span>
          {queueLeft > 0 ? (
            <span className="rounded bg-muted/50 px-1.5 py-0.5 text-[10px] text-muted-foreground">
              +{queueLeft} 待审
            </span>
          ) : null}
          <div className="ml-auto flex items-center gap-1">
            <Button
              type="button"
              size="sm"
              variant="secondary"
              className="h-7 gap-1 px-2 text-[11px]"
              onClick={() => onAccept(current.id)}
              title="保留磁盘上的变更"
            >
              <Check className="size-3.5" />
              接受
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="h-7 gap-1 px-2 text-[11px]"
              disabled={!canRevert}
              title={
                canRevert
                  ? "撤销磁盘变更"
                  : current.previousOmitted
                    ? "文件过大，无法自动撤销"
                    : "无法撤销（需本机工作区与预镜像）"
              }
              onClick={() => onReject(current.id)}
            >
              <RotateCcw className="size-3.5" />
              撤销
            </Button>
            <Button
              type="button"
              size="icon"
              variant="ghost"
              className="size-7"
              title="忽略"
              onClick={() => onDismiss(current.id)}
            >
              <X className="size-3.5" />
            </Button>
          </div>
        </div>
        <FileDiffBlock
          path={current.path}
          rows={current.rows}
          stats={current.stats}
          maxRows={48}
          defaultOpen
        />
      </div>
    </div>
  );
}

export default DiffDock;
