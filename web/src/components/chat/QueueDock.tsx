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

/** @deprecated Pending inbox UI moved into Composer. Kept as no-op for compatibility. */
export function QueueDock({ items, className }: QueueDockProps) {
  if (!items.length) return null;
  return (
    <div className={cn("hidden", className)} aria-hidden data-queue-dock-deprecated />
  );
}

export default QueueDock;
