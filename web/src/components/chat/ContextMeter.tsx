import { useMemo, useState } from "react";

import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { estimateContextOccupancy, formatCompactTokens } from "@/lib/contextEstimate";
import { cn } from "@/lib/utils";

const RADIUS = 5.5;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

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
  const dash = (CIRCUMFERENCE * percent) / 100;

  const fillClass =
    percent >= 90
      ? "stroke-[rgba(224,112,112,0.95)]"
      : percent >= 75
        ? "stroke-[rgba(232,176,72,0.95)]"
        : "stroke-muted-foreground/90";

  const barSegments = useMemo(() => {
    const b = occupancy.breakdown;
    const total = occupancy.contextWindow || 1;
    const rows = [
      { key: "system", label: "系统提示", tokens: b.systemTokens, color: "bg-[#7aa2c8]" },
      { key: "tools", label: "工具定义", tokens: b.toolsTokens, color: "bg-[#a78bfa]" },
      { key: "messages", label: "对话消息", tokens: b.messageTokens, color: "bg-[#3a9cf0]" },
      { key: "free", label: "剩余可用", tokens: b.freeTokens, color: "bg-foreground/15" },
    ];
    return rows
      .map((r) => ({
        ...r,
        width: Math.max(0, (r.tokens / total) * 100),
        display: formatCompactTokens(r.tokens),
      }))
      .filter((r) => r.tokens > 0 || r.key === "free");
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
              className="fill-none stroke-foreground/20"
              cx="7"
              cy="7"
              r={RADIUS}
              strokeWidth={2}
            />
            <circle
              className={cn("fill-none transition-all duration-180", fillClass)}
              cx="7"
              cy="7"
              r={RADIUS}
              strokeWidth={2}
              strokeLinecap="round"
              strokeDasharray={`${dash} ${CIRCUMFERENCE}`}
              transform="rotate(-90 7 7)"
            />
          </svg>
        </button>
      </PopoverTrigger>
      <PopoverContent
        align="end"
        side="top"
        className="w-[280px] p-3 text-xs leading-relaxed"
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

        <div className="my-2.5 flex h-1 overflow-hidden rounded-full bg-muted" aria-hidden>
          {barSegments.map((seg) => (
            <div
              key={seg.key}
              className={cn("h-full min-w-[2px] rounded-sm", seg.color)}
              style={{ width: `${Math.max(seg.width, seg.tokens ? 0.4 : 0)}%` }}
            />
          ))}
        </div>

        <dl className="m-0">
          {barSegments.map((seg) => (
            <div key={seg.key} className="flex justify-between gap-3 py-0.5">
              <dt className="flex items-center text-muted-foreground">
                <span className={cn("mr-1.5 inline-block size-2 rounded-sm", seg.color)} aria-hidden />
                {seg.label}
              </dt>
              <dd className="m-0 tabular-nums text-foreground">~{seg.display}</dd>
            </div>
          ))}
        </dl>
        <p className="mt-2.5 text-[10px] text-muted-foreground/85">
          估算值；按字符约 4∶1 换算，并结合模型窗口容量。
        </p>
      </PopoverContent>
    </Popover>
  );
}

export default ContextMeter;
