import { useMemo, useState } from "react";
import { ChevronRight } from "lucide-react";

import { GenericToolCard, type GenericToolCardProps } from "@/components/tools/GenericToolCard";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { pretty } from "@/lib/pretty";
import { cn } from "@/lib/utils";

function parseSearchPayload(raw: unknown) {
  if (!raw) return null;
  let data: any = raw;
  if (typeof raw === "string") {
    try {
      data = JSON.parse(raw);
    } catch {
      return null;
    }
  }
  if (data && typeof data === "object" && data.value && !data.results) {
    data = data.value;
  }
  if (!data || typeof data !== "object" || !Array.isArray(data.results)) return null;
  return data as { provider?: string; results: any[] };
}

export function WebSearchToolCard({
  item,
  nested = false,
  onInspect,
  onOpenChange,
  onStop,
}: GenericToolCardProps) {
  const searchPayload = useMemo(() => parseSearchPayload(item.result), [item.result]);
  const [open, setOpen] = useState(!!item.open);

  if (!searchPayload) {
    return (
      <GenericToolCard
        item={item}
        nested={nested}
        onInspect={onInspect}
        onOpenChange={onOpenChange}
        onStop={onStop}
      />
    );
  }

  const results = searchPayload.results || [];

  return (
    <Collapsible
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        item.open = next;
        onOpenChange?.(next);
      }}
      className={cn(
        "tool-card ok w-full max-w-full self-stretch rounded-lg border border-border/80 bg-card/40 text-sm",
        nested && "ml-0 border-dashed",
      )}
    >
      <CollapsibleTrigger asChild>
        <button
          type="button"
          className={cn(
            "flex w-full items-center gap-1.5 px-2 py-1.5 text-left hover:bg-muted/40",
            open && !nested && "border-b border-border/60",
          )}
        >
          <ChevronRight
            className={cn("size-3.5 shrink-0 text-muted-foreground transition-transform", open && "rotate-90")}
            aria-hidden
          />
          <Badge
            variant="outline"
            className="h-5 shrink-0 px-1.5 font-mono text-[10px] font-medium text-[hsl(var(--tool))]"
          >
            SEARCH
          </Badge>
          <span className="min-w-0 flex-1 truncate font-mono text-xs">{item.name}</span>
          <span className="shrink-0 font-mono text-[10px] text-muted-foreground">
            {searchPayload.provider || "web"} · {results.length} 条
          </span>
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent className="space-y-2 px-2.5 py-2">
        {item.arguments != null ? (
          <div className="space-y-1">
            <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Query</div>
            <pre className="max-h-40 overflow-auto whitespace-pre-wrap break-words rounded-md border border-border bg-background/50 p-2 font-mono text-[10.5px] text-muted-foreground">
              {pretty((item.arguments as any)?.query || item.arguments)}
            </pre>
          </div>
        ) : null}
        <div className="flex flex-col gap-1.5">
          {results.map((r: any, i: number) => (
            <a
              key={i}
              className="block rounded-lg border border-border bg-black/20 px-2 py-1.5 text-inherit no-underline hover:border-primary/40"
              href={r.url || "#"}
              target="_blank"
              rel="noopener noreferrer"
            >
              <div className="text-sm font-semibold text-[#7eb8f5]">{r.title || r.url || "result"}</div>
              {r.url ? (
                <div className="mt-0.5 break-all font-mono text-[10px] text-teal">{r.url}</div>
              ) : null}
              {r.snippet ? (
                <div className="mt-1 text-xs leading-snug text-muted-foreground">{r.snippet}</div>
              ) : null}
            </a>
          ))}
        </div>
        {item.activityId && onInspect ? (
          <div className="flex justify-end">
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-6 px-2 text-[10.5px]"
              onClick={(e) => {
                e.stopPropagation();
                onInspect(item.activityId!);
              }}
            >
              查看活动
            </Button>
          </div>
        ) : null}
      </CollapsibleContent>
    </Collapsible>
  );
}

export default WebSearchToolCard;
