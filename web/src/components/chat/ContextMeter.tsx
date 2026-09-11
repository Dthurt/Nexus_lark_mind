import { useMemo, useState } from "react";

import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  estimateContextOccupancy,
  formatCompactTokens,
  formatSharePercent,
} from "@/lib/contextEstimate";
import { cn } from "@/lib/utils";

const RADIUS = 5.5;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

const COMPOSITION = [
  { key: "system", label: "系统提示", tokenKey: "systemTokens", shareKey: "system", stroke: "#7aa2c8", swatch: "bg-[#7aa2c8]" },
  { key: "tools", label: "工具定义", tokenKey: "toolsTokens", shareKey: "tools", stroke: "#a78bfa", swatch: "bg-[#a78bfa]" },
  { key: "messages", label: "对话消息", tokenKey: "messageTokens", shareKey: "messages", stroke: "#3a9cf0", swatch: "bg-[#3a9cf0]" },
] as const;

export type ContextMeterProps = {
  items?: any[];
  tools?: any[];
  modelName?: string;
  cwd?: string;
  workspaceTitle?: string;
  lastPromptTokens?: number;
  draft?: string;
  className?: string;
};

export function ContextMeter({
  items = [],
  tools = [],
  modelName = "",
  cwd = "",
  workspaceTitle = "",
  lastPromptTokens = 0,
  draft = "",
  className,
}: ContextMeterProps) {
  const [open, setOpen] = useState(false);

  const occupancy = useMemo(
    () =>
      estimateContextOccupancy({
        items,
        tools,
        modelName,
        cwd,
        workspaceTitle,
        lastPromptTokens,
        draft,
      }),
    [items, tools, modelName, cwd, workspaceTitle, lastPromptTokens, draft],
  );

  const percent = occupancy.percent;

  /** Full-window segments for the ring (includes free gap as empty track). */
  const ringArcs = useMemo(() => {
    const parts = COMPOSITION.map((row) => {
      const tokens = occupancy.breakdown[row.tokenKey];
      const frac = occupancy.windowShares[row.shareKey];
      return {
        key: row.key,
        stroke: row.stroke,
        length: CIRCUMFERENCE * Math.max(0, frac),
        tokens,
      };
    }).filter((p) => p.length > 0.01);
    let offset = 0;
    return parts.map((p) => {
      const dashoffset = -offset;
      offset += p.length;
      return { ...p, dashoffset };
    });
  }, [occupancy]);

  /** Used-portion bar (DSH-style): composition fills `percent` of the track. */
  const barSegments = useMemo(() => {
    return COMPOSITION.map((row) => {
      const tokens = occupancy.breakdown[row.tokenKey];
      const usedShare = occupancy.usedShares[row.shareKey];
      const width = percent * usedShare;
      return {
        key: row.key,
        label: row.label,
        tokens,
        width,
        display: formatCompactTokens(tokens),
        shareLabel: formatSharePercent(occupancy.windowShares[row.shareKey]),
        usedLabel: formatSharePercent(usedShare),
        swatch: row.swatch,
      };
    }).filter((r) => r.tokens > 0 || r.width > 0.05);
  }, [occupancy, percent]);

  const legendRows = useMemo(() => {
    const usedRows = COMPOSITION.map((row) => {
      const tokens = occupancy.breakdown[row.tokenKey];
      return {
        key: row.key,
        label: row.label,
        tokens,
        display: formatCompactTokens(tokens),
        shareLabel: formatSharePercent(occupancy.windowShares[row.shareKey]),
        swatch: row.swatch,
      };
    });
    return [
      ...usedRows,
      {
        key: "free",
        label: "剩余可用",
        tokens: occupancy.freeTokens,
        display: formatCompactTokens(occupancy.freeTokens),
        shareLabel: formatSharePercent(occupancy.windowShares.free),
        swatch: "bg-foreground/15",
      },
    ];
  }, [occupancy]);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className={cn(
            "inline-grid size-7 shrink-0 place-items-center rounded-full border-0 bg-transparent p-0 text-muted-foreground hover:bg-muted",
            className,
          )}
          title={`上下文已用 ${percent}%（点击查看构成）`}
          aria-label={`上下文已用 ${percent}%`}
          aria-expanded={open}
          aria-haspopup="dialog"
        >
          <svg viewBox="0 0 14 14" width="14" height="14" aria-hidden>
            <circle
              className="fill-none stroke-foreground/15"
              cx="7"
              cy="7"
              r={RADIUS}
              strokeWidth={2}
            />
            {ringArcs.map((arc) => (
              <circle
                key={arc.key}
                className="fill-none transition-all duration-180"
                cx="7"
                cy="7"
                r={RADIUS}
                stroke={arc.stroke}
                strokeWidth={2}
                strokeLinecap="butt"
                strokeDasharray={`${arc.length} ${Math.max(0, CIRCUMFERENCE - arc.length)}`}
                strokeDashoffset={arc.dashoffset}
                transform="rotate(-90 7 7)"
              />
            ))}
          </svg>
        </button>
      </PopoverTrigger>
      <PopoverContent
        align="end"
        side="top"
        className="w-[300px] p-3 text-xs leading-relaxed"
        role="dialog"
        aria-label="上下文用量"
      >
        <div className="flex items-center gap-1.5">
          <span className="text-muted-foreground">上下文已用</span>
          <span className="font-semibold text-foreground">{percent}%</span>
          <span className="ml-auto font-medium tabular-nums text-foreground">
            ~{formatCompactTokens(occupancy.usedTokens)} /{" "}
            {formatCompactTokens(occupancy.contextWindow)}
          </span>
        </div>

        <div className="my-2.5 flex h-1.5 overflow-hidden rounded-full bg-muted" aria-hidden>
          {barSegments.map((seg) => (
            <div
              key={seg.key}
              className={cn("h-full min-w-[2px]", seg.swatch)}
              style={{ width: `${Math.max(seg.width, seg.tokens ? 0.5 : 0)}%` }}
              title={`${seg.label} ${seg.usedLabel}`}
            />
          ))}
        </div>

        <dl className="m-0">
          {legendRows.map((seg) => (
            <div key={seg.key} className="flex justify-between gap-3 py-0.5">
              <dt className="flex min-w-0 items-center text-muted-foreground">
                <span className={cn("mr-1.5 inline-block size-2 shrink-0 rounded-sm", seg.swatch)} aria-hidden />
                <span className="truncate">{seg.label}</span>
              </dt>
              <dd className="m-0 flex shrink-0 items-baseline gap-2 tabular-nums text-foreground">
                <span className="text-muted-foreground">{seg.shareLabel}</span>
                <span>~{seg.display}</span>
              </dd>
            </div>
          ))}
        </dl>
        <p className="mt-2.5 text-[10px] text-muted-foreground/85">
          构成含系统提示、工具定义与对话消息；占比相对模型窗口。估算约 4 字/token。
        </p>
      </PopoverContent>
    </Popover>
  );
}

export default ContextMeter;
