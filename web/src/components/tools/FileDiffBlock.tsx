import { useState } from "react";
import { ChevronRight } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { formatDiffStats } from "@/lib/lineDiff";
import { cn } from "@/lib/utils";

export type DiffRow = {
  type: "add" | "del" | "ctx" | string;
  text: string;
  oldLine?: number | null;
  newLine?: number | null;
};

export type FileDiffBlockProps = {
  path?: string;
  rows?: DiffRow[];
  stats?: { adds?: number; dels?: number };
  maxRows?: number;
  defaultOpen?: boolean;
  className?: string;
};

export function FileDiffBlock({
  path = "",
  rows = [],
  stats = { adds: 0, dels: 0 },
  maxRows = 80,
  defaultOpen = true,
  className,
}: FileDiffBlockProps) {
  const [open, setOpen] = useState(defaultOpen);
  const [expanded, setExpanded] = useState(false);

  const truncated = rows.length > maxRows && !expanded;
  const visibleRows = truncated ? rows.slice(0, maxRows) : rows;
  const hiddenCount = Math.max(0, rows.length - maxRows);
  const statsText = formatDiffStats(stats);

  return (
    <Collapsible
      open={open}
      onOpenChange={setOpen}
      className={cn(
        "file-diff overflow-hidden rounded-lg border border-border bg-black/20",
        className,
      )}
    >
      <CollapsibleTrigger asChild>
        <button
          type="button"
          className={cn(
            "flex w-full items-center gap-2 px-2 py-1.5 text-left text-xs text-muted-foreground",
            open && "border-b border-border",
          )}
        >
          <ChevronRight
            className={cn("size-3 shrink-0 transition-transform", open && "rotate-90")}
            aria-hidden
          />
          <span className="min-w-0 flex-1 truncate font-mono text-foreground">
            {path || "file"}
          </span>
          <span className="ml-auto inline-flex shrink-0 gap-1.5 font-mono">
            {stats.adds ? <span className="font-semibold text-[#3fb950]">+{stats.adds}</span> : null}
            {stats.dels ? <span className="font-semibold text-[#f85149]">−{stats.dels}</span> : null}
            {!stats.adds && !stats.dels ? <span>{statsText}</span> : null}
          </span>
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="max-h-[360px] overflow-auto font-mono text-[11px] leading-snug" role="table" aria-label="文件变更">
          {visibleRows.map((row, idx) => (
            <div
              key={idx}
              className={cn(
                "grid grid-cols-[14px_36px_36px_minmax(0,1fr)] whitespace-pre pr-1",
                row.type === "add" && "bg-[rgba(46,160,67,0.18)]",
                row.type === "del" && "bg-[rgba(248,81,73,0.18)]",
              )}
              role="row"
            >
              <span
                className={cn(
                  "text-center text-muted-foreground select-none",
                  row.type === "add" && "text-[#6ee7b7]",
                  row.type === "del" && "text-[#f0a0a0]",
                )}
                aria-hidden
              >
                {row.type === "add" ? "+" : row.type === "del" ? "−" : " "}
              </span>
              <span className="select-none border-r border-white/5 px-1.5 text-right text-muted-foreground/55">
                {row.oldLine ?? ""}
              </span>
              <span className="select-none border-r border-white/5 px-1.5 text-right text-muted-foreground/55">
                {row.newLine ?? ""}
              </span>
              <code className="min-w-0 overflow-x-auto border-0 bg-transparent px-2 font-inherit text-foreground whitespace-pre">
                {row.text}
              </code>
            </div>
          ))}
          {truncated ? (
            <Button
              type="button"
              variant="ghost"
              className="h-auto w-full justify-start rounded-none border-t border-border px-2 py-1.5 text-xs text-muted-foreground hover:text-primary"
              onClick={() => setExpanded(true)}
            >
              展开其余 {hiddenCount} 行…
            </Button>
          ) : rows.length > maxRows ? (
            <Button
              type="button"
              variant="ghost"
              className="h-auto w-full justify-start rounded-none border-t border-border px-2 py-1.5 text-xs text-muted-foreground hover:text-primary"
              onClick={() => setExpanded(false)}
            >
              收起
            </Button>
          ) : null}
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}

export default FileDiffBlock;
