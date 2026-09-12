import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { InboxItem } from "@/api/endpoints";

export type QueueDockProps = {
  items: InboxItem[];
  busyEnterMode?: "queue" | "steer";
  onRemove: (id: string) => void;
  className?: string;
};

/** Pending steer / queue messages above the composer (DSH-inspired). */
export function QueueDock({
  items,
  busyEnterMode = "queue",
  onRemove,
  className,
}: QueueDockProps) {
  if (!items.length) return null;

  return (
    <div
      className={cn(
        "border-border/70 bg-card/95 mx-3 mb-1 rounded-lg border px-3 py-2 shadow-sm backdrop-blur",
        className,
      )}
    >
      <div className="text-muted-foreground mb-1.5 flex items-center justify-between text-[11px]">
        <span>
          待处理 · Enter 默认{" "}
          <span className="text-foreground font-medium">
            {busyEnterMode === "steer" ? "中途引导" : "排队"}
          </span>
          （Ctrl+Enter 切换）
        </span>
        <span>{items.length}</span>
      </div>
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
    </div>
  );
}
