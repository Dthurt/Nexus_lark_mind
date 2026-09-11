import { useMemo, useState } from "react";
import { ChevronRight } from "lucide-react";

import { ToolCard } from "@/components/chat/ToolCard";
import { Badge } from "@/components/ui/badge";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import type { ToolCardItem } from "@/components/tools/toolRegistry";
import { cn } from "@/lib/utils";

export type ToolCallGroupProps = {
  tools: ToolCardItem[];
  onInspect?: (activityId: string) => void;
  className?: string;
};

function shortName(name?: string) {
  const raw = String(name || "tool");
  return raw.replace(/^builtin_workspace_/, "").replace(/^cli_/, "").split(".").pop();
}

export function ToolCallGroup({ tools, onInspect, className }: ToolCallGroupProps) {
  const [open, setOpen] = useState(false);

  const summaryLabel = useMemo(() => {
    const names = tools.map((t) => shortName(t.name));
    const unique: string[] = [];
    for (const n of names) {
      if (n && !unique.includes(n)) unique.push(n);
    }
    const preview = unique.slice(0, 4).join(" · ");
    const n = tools.length;
    if (n <= 1) return preview || "tool";
    return `${n} 个工具 · ${preview}${unique.length > 4 ? "…" : ""}`;
  }, [tools]);

  const hasFail = tools.some(
    (t) => t.status === "fail" || t.error != null || (t as any).success === false,
  );
  const pending = tools.some(
    (t) => t.result == null && t.error == null && (t as any).success == null,
  );

  return (
    <Collapsible
      open={open}
      onOpenChange={setOpen}
      className={cn(
        "tool-group w-fit max-w-[min(100%,560px)] self-start animate-in fade-in duration-150",
        open &&
          "w-[min(100%,560px)] rounded-lg border border-[hsl(var(--tool))]/25 bg-[hsl(var(--tool))]/5",
        className,
      )}
    >
      <CollapsibleTrigger asChild>
        <button
          type="button"
          className={cn(
            "inline-flex items-center gap-1.5 rounded-full border border-border bg-white/5 px-2.5 py-1 text-sm font-medium text-muted-foreground",
            "hover:border-white/15 hover:text-foreground",
            open && "flex w-full rounded-none border-0 bg-transparent text-foreground",
            !hasFail && !pending && "border-teal/30",
            hasFail && "border-destructive/35",
            pending && "border-[hsl(var(--tool))]/35",
          )}
        >
          <ChevronRight
            className={cn("size-3.5 shrink-0 transition-transform", open && "rotate-90")}
            aria-hidden
          />
          <Badge
            variant="outline"
            className="h-5 border-0 bg-[hsl(var(--tool))]/15 px-1.5 font-mono text-[10px] text-[hsl(var(--tool))]"
          >
            {pending ? "RUN" : hasFail ? "ERR" : "TOOLS"}
          </Badge>
          <span className="min-w-0 truncate font-mono text-sm">{summaryLabel}</span>
          {pending ? (
            <span className="ml-auto text-xs text-muted-foreground">运行中</span>
          ) : hasFail ? (
            <span className="ml-auto text-xs text-muted-foreground">有失败</span>
          ) : null}
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent className="flex flex-col gap-1.5 px-2.5 pb-2.5 pt-0.5">
        {tools.map((t) => (
          <ToolCard
            key={(t as any).id || t.callId || t.name}
            item={t}
            nested
            onInspect={onInspect}
          />
        ))}
      </CollapsibleContent>
    </Collapsible>
  );
}

export default ToolCallGroup;
