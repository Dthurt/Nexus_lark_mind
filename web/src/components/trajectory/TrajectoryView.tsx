import { useEffect, useMemo, useRef, useState } from "react";

import { cn } from "@/lib/utils";
import "./TrajectoryView.css";

export type TrajectoryRow = {
  id: string;
  seq?: number;
  kind?: string;
  title?: string;
  summary?: string;
  phase?: string;
  error?: boolean;
  durationMs?: number | null;
  activityId?: string | null;
  [key: string]: unknown;
};

export type TrajectoryViewProps = {
  rows?: TrajectoryRow[];
  followTail?: boolean;
  selectedId?: string | null;
  onFollowTailChange?: (v: boolean) => void;
  onSelect?: (id: string) => void;
  onInspect?: (row: TrajectoryRow) => void;
  className?: string;
};

const KIND_FILTERS = ["all", "tool", "model", "system", "error"] as const;

function kindClass(row: TrajectoryRow) {
  return cn(
    `tr-${row.kind || "system"}`,
    row.error && "tr-error",
    row.phase && `tr-${row.phase}`,
  );
}

function matchesFilter(row: TrajectoryRow, filter: string) {
  if (filter === "all") return true;
  if (filter === "error") return !!row.error;
  return String(row.kind || "").toLowerCase().includes(filter);
}

export function TrajectoryView({
  rows = [],
  followTail = true,
  selectedId = null,
  onFollowTailChange,
  onSelect,
  onInspect,
  className,
}: TrajectoryViewProps) {
  const scrollerRef = useRef<HTMLDivElement>(null);
  const [userPinned, setUserPinned] = useState(false);
  const [filter, setFilter] = useState<(typeof KIND_FILTERS)[number]>("all");

  const visible = useMemo(
    () => rows.filter((r) => matchesFilter(r, filter)),
    [rows, filter],
  );

  useEffect(() => {
    if (!followTail || userPinned) return;
    const el = scrollerRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [visible.length, followTail, userPinned]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      if (e.key !== "j" && e.key !== "k") return;
      if (!visible.length) return;
      e.preventDefault();
      const idx = Math.max(
        0,
        visible.findIndex((r) => r.id === selectedId),
      );
      const next =
        e.key === "j"
          ? visible[Math.min(visible.length - 1, (idx < 0 ? 0 : idx) + 1)]
          : visible[Math.max(0, (idx < 0 ? 0 : idx) - 1)];
      if (!next) return;
      onSelect?.(next.id);
      onInspect?.(next);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [visible, selectedId, onSelect, onInspect]);

  const onScroll = () => {
    const el = scrollerRef.current;
    if (!el) return;
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 48;
    setUserPinned(!nearBottom);
    onFollowTailChange?.(nearBottom);
  };

  return (
    <div className={cn("trajectory", className)}>
      <div className="traj-toolbar">
        <span className="traj-label">Trajectory · 事件账本</span>
        <div className="flex flex-wrap items-center gap-1">
          {KIND_FILTERS.map((k) => (
            <button
              key={k}
              type="button"
              className={cn(
                "rounded border px-1.5 py-0.5 font-mono text-[10px] uppercase",
                filter === k
                  ? "border-primary/40 bg-primary/15 text-foreground"
                  : "border-border text-muted-foreground hover:text-foreground",
              )}
              onClick={() => setFilter(k)}
            >
              {k}
            </button>
          ))}
        </div>
        <label className="traj-follow">
          <input
            type="checkbox"
            checked={followTail && !userPinned}
            onChange={(e) => {
              const checked = e.target.checked;
              onFollowTailChange?.(checked);
              setUserPinned(!checked);
            }}
          />
          跟随尾部
        </label>
      </div>
      <div ref={scrollerRef} className="traj-list" onScroll={onScroll}>
        {!visible.length ? (
          <div className="traj-empty">
            {rows.length ? "当前筛选无事件。" : "发送消息后，此处按回合记录工具与回复。"}
          </div>
        ) : (
          visible.map((row) => (
            <button
              key={row.id}
              type="button"
              className={cn("traj-row", kindClass(row), selectedId === row.id && "selected")}
              onClick={() => {
                onSelect?.(row.id);
                onInspect?.(row);
              }}
            >
              <span className="traj-idx">#{row.seq}</span>
              <span className="traj-kind">{row.kind}</span>
              <span className="traj-sum">{row.summary || row.title}</span>
              {row.durationMs != null ? (
                <span className="traj-meta">{Number(row.durationMs).toFixed(0)}ms</span>
              ) : null}
            </button>
          ))
        )}
      </div>
    </div>
  );
}

export default TrajectoryView;
