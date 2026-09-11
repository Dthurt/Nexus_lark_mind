import { useEffect, useRef, useState } from "react";

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

function kindClass(row: TrajectoryRow) {
  return cn(
    `tr-${row.kind || "system"}`,
    row.error && "tr-error",
    row.phase && `tr-${row.phase}`,
  );
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

  useEffect(() => {
    if (!followTail || userPinned) return;
    const el = scrollerRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [rows.length, followTail, userPinned]);

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
        {!rows.length ? (
          <div className="traj-empty">发送消息后，此处按回合记录工具与回复。</div>
        ) : (
          rows.map((row) => (
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
