import { MessageSquare, TrendingUp } from "lucide-react";

import { cn } from "@/lib/utils";

export type CenterViewId = "chat" | "trajectory" | string;

export type ViewRingItem = {
  id: CenterViewId;
  label: string;
  icon?: "chat" | "trajectory" | string;
};

export type ViewRingProps = {
  value?: CenterViewId;
  onChange?: (id: CenterViewId) => void;
  views?: ViewRingItem[];
  className?: string;
};

const DEFAULT_VIEWS: ViewRingItem[] = [
  { id: "chat", label: "对话", icon: "chat" },
  { id: "trajectory", label: "轨迹", icon: "trajectory" },
];

export function ViewRing({
  value = "chat",
  onChange,
  views = DEFAULT_VIEWS,
  className,
}: ViewRingProps) {
  return (
    <div
      className={cn(
        "inline-flex gap-0.5 rounded-lg border border-border bg-muted/40 p-0.5",
        className,
      )}
      role="tablist"
      aria-label="会话视图"
    >
      {views.map((v) => {
        const active = value === v.id;
        const isTrajectory = v.icon === "trajectory" || v.id === "trajectory";
        const Icon = isTrajectory ? TrendingUp : MessageSquare;
        return (
          <button
            key={v.id}
            type="button"
            role="tab"
            aria-selected={active}
            title={v.label}
            aria-label={v.label}
            className={cn(
              "inline-flex size-7 items-center justify-center rounded-md text-muted-foreground transition-colors",
              "hover:text-foreground",
              active && "bg-primary/15 text-primary",
            )}
            onClick={() => onChange?.(v.id)}
          >
            <Icon className="size-[15px]" aria-hidden />
          </button>
        );
      })}
    </div>
  );
}

export default ViewRing;
