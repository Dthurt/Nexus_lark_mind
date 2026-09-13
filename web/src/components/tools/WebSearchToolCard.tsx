import { useMemo, useState } from "react";

import { GenericToolCard, type GenericToolCardProps } from "@/components/tools/GenericToolCard";
import { ToolChipShell } from "@/components/tools/ToolChipShell";
import { pretty } from "@/lib/pretty";
import { oneLinePreview, shortToolName } from "@/lib/toolChip";
import { resolveToolStatus } from "@/lib/toolStatus";

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
  highlighted = false,
  onInspect,
  onOpenChange,
  onStop,
}: GenericToolCardProps) {
  const searchPayload = useMemo(() => parseSearchPayload(item.result), [item.result]);
  const [open, setOpen] = useState(!!item.open);
  const runStatus = resolveToolStatus(item);

  if (!searchPayload) {
    return (
      <GenericToolCard
        item={{ ...item, badge: item.badge || "SEARCH" }}
        nested={nested}
        highlighted={highlighted}
        onInspect={onInspect}
        onOpenChange={onOpenChange}
        onStop={onStop}
      />
    );
  }

  const results = searchPayload.results || [];
  const query =
    (item.arguments as any)?.query != null
      ? String((item.arguments as any).query)
      : oneLinePreview(item.arguments, 64);
  const summary = `${searchPayload.provider || "web"} · ${results.length} 条${
    query ? ` · ${query.slice(0, 40)}` : ""
  }`;

  return (
    <ToolChipShell
      callId={item.callId}
      status={runStatus}
      badge="SEARCH"
      title={shortToolName(item.name)}
      summary={summary}
      durationMs={item.durationMs}
      nested={nested}
      highlighted={highlighted}
      defaultOpen={open || !!item.open}
      onOpenChange={(next) => {
        setOpen(next);
        item.open = next;
        onOpenChange?.(next);
      }}
      onStop={() => onStop?.(item.callId)}
      fullName={item.name}
      openaiName={item.openaiName}
      approvalDecision={item.approvalDecision}
      activityId={item.activityId}
      onInspect={onInspect}
    >
      {item.arguments != null ? (
        <div className="space-y-0.5">
          <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Query</div>
          <pre className="max-h-40 overflow-auto whitespace-pre-wrap break-words rounded-md border border-border/50 bg-background/35 p-2 font-mono text-[10.5px] text-muted-foreground">
            {pretty((item.arguments as any)?.query || item.arguments)}
          </pre>
        </div>
      ) : null}
      <div className="flex flex-col gap-1">
        {results.map((r: any, i: number) => (
          <a
            key={i}
            className="block rounded-md border border-border/60 bg-foreground/[0.03] px-2 py-1.5 text-inherit no-underline hover:border-primary/35"
            href={r.url || "#"}
            target="_blank"
            rel="noopener noreferrer"
          >
            <div className="text-[12.5px] font-medium text-sky-300/90">{r.title || r.url || "result"}</div>
            {r.url ? (
              <div className="mt-0.5 break-all font-mono text-[10px] text-teal">{r.url}</div>
            ) : null}
            {r.snippet ? (
              <div className="mt-1 text-[11px] leading-snug text-muted-foreground">{r.snippet}</div>
            ) : null}
          </a>
        ))}
      </div>
    </ToolChipShell>
  );
}

export default WebSearchToolCard;
