import { useEffect, useMemo, useRef, useState } from "react";

import { cn } from "@/lib/utils";
import type { TrajectoryRow } from "@/hooks/useTrajectory";
import "./TrajectoryView.css";

export type { TrajectoryRow };

export type TrajectoryViewProps = {
  rows?: TrajectoryRow[];
  followTail?: boolean;
  selectedId?: string | null;
  onFollowTailChange?: (v: boolean) => void;
  onSelect?: (id: string) => void;
  onInspect?: (row: TrajectoryRow) => void;
  className?: string;
};

const KIND_FILTERS = [
  "all",
  "tool",
  "message",
  "reasoning",
  "subagent",
  "system",
  "error",
] as const;

type TurnGroup = {
  turn: number;
  title: string;
  headerId: string | null;
  rows: TrajectoryRow[];
  spanStart: number | null;
  spanEnd: number | null;
};

function kindClass(row: TrajectoryRow) {
  return cn(
    `tr-${row.kind || "system"}`,
    row.error && "tr-error",
    row.phase && `tr-${row.phase}`,
    row.phase === "running" && "tr-running",
  );
}

function matchesFilter(row: TrajectoryRow, filter: string) {
  if (row.kind === "turn" || row.kind === "turn-end") return false;
  if (filter === "all") return true;
  if (filter === "error") return !!row.error;
  if (filter === "message") return row.kind === "message" || row.kind === "user";
  return String(row.kind || "").toLowerCase() === filter;
}

function matchesSearch(row: TrajectoryRow, q: string) {
  if (!q) return true;
  const hay = [
    row.kind,
    row.title,
    row.summary,
    typeof row.detail === "string" ? row.detail : "",
    row.callId,
    row.openaiName,
  ]
    .filter(Boolean)
    .join("\n")
    .toLowerCase();
  return hay.includes(q);
}

function formatMs(ms: number | null | undefined) {
  if (ms == null || !Number.isFinite(ms)) return null;
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(ms >= 10_000 ? 0 : 1)}s`;
}

function groupByTurn(rows: TrajectoryRow[]): TurnGroup[] {
  const groups: TurnGroup[] = [];
  let current: TurnGroup | null = null;

  const open = (turn: number, title: string, headerId: string | null): TurnGroup => {
    const g: TurnGroup = {
      turn,
      title,
      headerId,
      rows: [],
      spanStart: null,
      spanEnd: null,
    };
    groups.push(g);
    current = g;
    return g;
  };

  for (const row of rows) {
    if (row.kind === "turn" || row.opensTurn) {
      open(row.turn || groups.length + 1, String(row.title || `Turn #${row.turn}`), row.id);
      continue;
    }
    if (row.kind === "turn-end") {
      if (!current) open(row.turn || groups.length + 1, `Turn #${row.turn || "?"}`, null);
      continue;
    }
    const g = current ?? open(row.turn || 1, `Turn #${row.turn || 1}`, null);
    g.rows.push(row);
    const start = row.startedAt ?? row.at;
    const end =
      row.durationMs != null && start != null
        ? Number(start) + Number(row.durationMs)
        : row.at;
    if (start != null) {
      g.spanStart = g.spanStart == null ? Number(start) : Math.min(g.spanStart, Number(start));
    }
    if (end != null) {
      g.spanEnd = g.spanEnd == null ? Number(end) : Math.max(g.spanEnd, Number(end));
    }
  }
  return groups.filter((g) => g.rows.length > 0 || g.headerId);
}

function TimingBar({
  groups,
  focusTurn,
  onFocusTurn,
}: {
  groups: TurnGroup[];
  focusTurn: number | null;
  onFocusTurn: (turn: number | null) => void;
}) {
  const spans = useMemo(() => {
    const timed = groups.filter((g) => g.spanStart != null && g.spanEnd != null);
    if (!timed.length) return [];
    const min = Math.min(...timed.map((g) => g.spanStart!));
    const max = Math.max(...timed.map((g) => g.spanEnd!));
    const range = Math.max(1, max - min);
    return timed.map((g) => ({
      turn: g.turn,
      title: g.title,
      left: ((g.spanStart! - min) / range) * 100,
      width: Math.max(2, ((g.spanEnd! - g.spanStart!) / range) * 100),
      ms: g.spanEnd! - g.spanStart!,
    }));
  }, [groups]);

  if (!spans.length) return null;

  return (
    <div className="traj-timing" role="img" aria-label="回合耗时概览">
      <div className="traj-timing-track">
        {spans.map((s) => (
          <button
            key={s.turn}
            type="button"
            className={cn("traj-timing-seg", focusTurn === s.turn && "active")}
            style={{ left: `${s.left}%`, width: `${s.width}%` }}
            title={`${s.title} · ${formatMs(s.ms)}`}
            onClick={() => onFocusTurn(focusTurn === s.turn ? null : s.turn)}
          />
        ))}
      </div>
      <div className="traj-timing-legend">
        {focusTurn != null ? (
          <button type="button" className="traj-linkish" onClick={() => onFocusTurn(null)}>
            清除时间聚焦 · Turn #{focusTurn}
          </button>
        ) : (
          <span>点击色块聚焦回合</span>
        )}
      </div>
    </div>
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
  const [filter, setFilter] = useState<(typeof KIND_FILTERS)[number]>("all");
  const [query, setQuery] = useState("");
  const [collapsed, setCollapsed] = useState<Record<number, boolean>>({});
  const [allCollapsed, setAllCollapsed] = useState(false);
  const [focusTurn, setFocusTurn] = useState<number | null>(null);

  const groups = useMemo(() => groupByTurn(rows), [rows]);
  const q = query.trim().toLowerCase();

  const visibleGroups = useMemo(() => {
    return groups
      .map((g) => ({
        ...g,
        rows: g.rows.filter(
          (r) =>
            matchesFilter(r, filter) &&
            matchesSearch(r, q) &&
            (focusTurn == null || g.turn === focusTurn),
        ),
      }))
      .filter((g) => g.rows.length > 0 || (!q && filter === "all" && focusTurn == null));
  }, [groups, filter, q, focusTurn]);

  const flatVisible = useMemo(
    () => visibleGroups.flatMap((g) => (collapsed[g.turn] || allCollapsed ? [] : g.rows)),
    [visibleGroups, collapsed, allCollapsed],
  );

  useEffect(() => {
    if (!followTail || userPinned) return;
    const el = scrollerRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [flatVisible.length, rows.length, followTail, userPinned]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      if (e.key !== "j" && e.key !== "k") return;
      if (!flatVisible.length) return;
      e.preventDefault();
      const idx = Math.max(
        0,
        flatVisible.findIndex((r) => r.id === selectedId),
      );
      const next =
        e.key === "j"
          ? flatVisible[Math.min(flatVisible.length - 1, (idx < 0 ? 0 : idx) + 1)]
          : flatVisible[Math.max(0, (idx < 0 ? 0 : idx) - 1)];
      if (!next) return;
      onSelect?.(next.id);
      onInspect?.(next);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [flatVisible, selectedId, onSelect, onInspect]);

  const onScroll = () => {
    const el = scrollerRef.current;
    if (!el) return;
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 48;
    setUserPinned(!nearBottom);
    onFollowTailChange?.(nearBottom);
  };

  const toggleTurn = (turn: number) => {
    setCollapsed((prev) => ({ ...prev, [turn]: !prev[turn] }));
  };

  return (
    <div className={cn("trajectory", className)}>
      <div className="traj-toolbar">
        <span className="traj-label">Trajectory · 事件账本</span>
        <div className="traj-toolbar-actions">
          <input
            className="traj-search"
            type="search"
            value={query}
            placeholder="搜索…"
            aria-label="搜索轨迹"
            onChange={(e) => setQuery(e.target.value)}
          />
          <button
            type="button"
            className={cn("traj-chip", allCollapsed && "active")}
            title={allCollapsed ? "展开全部回合" : "折叠全部回合"}
            onClick={() => setAllCollapsed((v) => !v)}
          >
            {allCollapsed ? "展开回合" : "折叠回合"}
          </button>
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
      </div>

      <div className="flex flex-wrap items-center gap-1 px-0.5">
        {KIND_FILTERS.map((k) => (
          <button
            key={k}
            type="button"
            className={cn("traj-chip", filter === k && "active")}
            onClick={() => setFilter(k)}
          >
            {k}
          </button>
        ))}
      </div>

      <TimingBar groups={groups} focusTurn={focusTurn} onFocusTurn={setFocusTurn} />

      <div ref={scrollerRef} className="traj-list" onScroll={onScroll}>
        {!visibleGroups.length ? (
          <div className="traj-empty">
            {rows.length ? "当前筛选无事件。" : "发送消息后，此处按回合记录工具与回复。"}
          </div>
        ) : (
          visibleGroups.map((g) => {
            const isCollapsed = allCollapsed || !!collapsed[g.turn];
            return (
              <section key={`turn-${g.turn}-${g.headerId || "x"}`} className="traj-turn">
                <button
                  type="button"
                  className="traj-turn-head"
                  onClick={() => toggleTurn(g.turn)}
                  aria-expanded={!isCollapsed}
                >
                  <span className="traj-turn-caret" aria-hidden>
                    {isCollapsed ? "▸" : "▾"}
                  </span>
                  <span className="traj-turn-title">{g.title}</span>
                  <span className="traj-turn-meta">
                    {g.rows.length} 事件
                    {g.spanStart != null && g.spanEnd != null
                      ? ` · ${formatMs(g.spanEnd - g.spanStart)}`
                      : ""}
                  </span>
                </button>
                {!isCollapsed &&
                  g.rows.map((row) => (
                    <button
                      key={row.id}
                      type="button"
                      className={cn(
                        "traj-row",
                        kindClass(row),
                        selectedId === row.id && "selected",
                      )}
                      onClick={() => {
                        onSelect?.(row.id);
                        onInspect?.(row);
                      }}
                    >
                      <span className="traj-idx">#{row.seq}</span>
                      <span className="traj-kind">{row.kind}</span>
                      <span className="traj-sum">{row.summary || row.title}</span>
                      <span className="traj-meta">
                        {row.phase === "running"
                          ? "…"
                          : formatMs(row.durationMs) || ""}
                      </span>
                    </button>
                  ))}
              </section>
            );
          })
        )}
      </div>
    </div>
  );
}

export default TrajectoryView;
