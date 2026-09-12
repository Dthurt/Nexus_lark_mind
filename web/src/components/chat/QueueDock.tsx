import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { InboxItem } from "@/api/endpoints";

export type QueueDockProps = {
  items: InboxItem[];
  busyEnterMode?: "queue" | "steer";
  busy?: boolean;
  onBusyEnterModeChange?: (mode: "queue" | "steer") => void;
  onRemove: (id: string) => void;
  className?: string;
};

/** Pending steer / queue messages above the composer (DSH-inspired). */
export function QueueDock({
  items,
  busyEnterMode = "queue",
  busy = false,
  onBusyEnterModeChange,
  onRemove,
  className,
}: QueueDockProps) {
  if (!items.length && !busy) return null;

  return (
    <div
      className={cn(
        "border-border/70 bg-card/95 mx-3 mb-1 rounded-lg border px-3 py-2 shadow-sm backdrop-blur",
        className,
      )}
    >
      <div className="text-muted-foreground mb-1.5 flex flex-wrap items-center justify-between gap-2 text-[11px]">
        <span>
          {items.length ? "待处理 · " : "Agent 忙碌中 · "}
          Enter 默认{" "}
          <span className="text-foreground font-medium">
            {busyEnterMode === "steer" ? "中途引导" : "排队"}
          </span>
          （Ctrl+Enter 临时切换）
        </span>
        <span className="inline-flex items-center gap-2">
          {onBusyEnterModeChange ? (
            <span className="inline-flex rounded border border-border/60 p-0.5">
              <button
                type="button"
                className={cn(
                  "rounded px-1.5 py-0.5",
                  busyEnterMode === "steer" && "bg-violet-500/20 text-violet-200",
                )}
                onClick={() => onBusyEnterModeChange("steer")}
              >
                引导
              </button>
              <button
                type="button"
                className={cn(
                  "rounded px-1.5 py-0.5",
                  busyEnterMode === "queue" && "bg-sky-500/20 text-sky-200",
                )}
                onClick={() => onBusyEnterModeChange("queue")}
              >
                排队
              </button>
            </span>
          ) : null}
          <span>{items.length}</span>
        </span>
      </div>
      {!items.length ? (
        <p className="text-muted-foreground m-0 text-[12px]">
          输入后按 Enter：
          {busyEnterMode === "steer"
            ? "会在下一个模型步骤前注入（真正中途打断）。"
            : "会等本轮结束后再发（排队，不是立刻打断）。"}
        </p>
      ) : (
        <ul className="flex max-h-28 flex-col gap-1 overflow-y-auto">
          {items.map((it) => (
            <li
              key={it.id}
              className="bg-muted/40 flex items-start gap-2 rounded-md px-2 py-1.5 text-[12px]"
            >
              <span
                className={cn(
                  "mt-0.5 shrink-0 rounded px-1 py-0.5 text-[10px] font-medium uppercase tracking-wide",
                  it.kind === "steer"
                    ? "bg-violet-500/15 text-violet-700 dark:text-violet-300"
                    : "bg-sky-500/15 text-sky-700 dark:text-sky-300",
                )}
              >
                {it.kind === "steer" ? "引导" : "排队"}
              </span>
              <span className="text-foreground/90 min-w-0 flex-1 whitespace-pre-wrap break-words">
                {it.content}
              </span>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="text-muted-foreground h-6 shrink-0 px-1.5 text-[11px]"
                onClick={() => onRemove(it.id)}
              >
                撤销
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
