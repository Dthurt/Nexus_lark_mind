import { useMemo } from "react";

import { ToolChipShell } from "@/components/tools/ToolChipShell";
import type { GenericToolCardProps } from "@/components/tools/GenericToolCard";
import { pretty } from "@/lib/pretty";
import { oneLinePreview, shortToolName } from "@/lib/toolChip";
import { resolveToolStatus } from "@/lib/toolStatus";

function parseResult(raw: unknown): Record<string, any> | null {
  if (raw == null) return null;
  if (typeof raw === "object") return raw as Record<string, any>;
  if (typeof raw === "string") {
    try {
      const data = JSON.parse(raw);
      return data && typeof data === "object" ? data : null;
    } catch {
      return null;
    }
  }
  return null;
}

const TITLES: Record<string, string> = {
  office_create: "创建文档",
  office_append: "写入一节",
  office_revise_plan: "修订结构",
  office_replace: "替换一块",
  office_save: "保存文档",
};

export function OfficeToolCard({
  item,
  nested = false,
  highlighted = false,
  onInspect,
  onOpenChange,
  onStop,
}: GenericToolCardProps) {
  const result = useMemo(() => parseResult(item.result), [item.result]);
  const status = resolveToolStatus(item);
  const leaf = shortToolName(item.name);
  const title = TITLES[leaf] || leaf;
  const counts = result?.outline?.counts;
  const summary = item.error
    ? oneLinePreview(item.error, 72)
    : status === "running"
      ? "正在写入…"
      : oneLinePreview(
          [result?.title, result?.file_name || result?.path, counts ? `${counts.blocks || 0} 段` : ""]
            .filter(Boolean)
            .join(" · ") || result?.hint,
          88,
        );

  return (
    <ToolChipShell
      callId={item.callId}
      status={status}
      badge="DOC"
      title={title}
      summary={summary}
      durationMs={item.durationMs}
      nested={nested}
      highlighted={highlighted}
      defaultOpen={!!item.open}
      onOpenChange={onOpenChange}
      onStop={() => onStop?.(item.callId)}
      fullName={item.name}
      openaiName={item.openaiName}
      approvalDecision={item.approvalDecision}
      activityId={item.activityId}
      onInspect={onInspect}
    >
      {result?.path || result?.download_url ? (
        <p className="m-0 font-mono text-[11px] text-teal">
          {String(result.path || result.file_name || "")}
          {result.download_url ? ` · ${result.download_url}` : ""}
        </p>
      ) : null}
      {result?.hint ? <p className="m-0 text-[11px] text-muted-foreground">{String(result.hint)}</p> : null}
      {item.error != null ? (
        <pre className="max-h-32 overflow-auto whitespace-pre-wrap rounded-md border border-rose-500/25 bg-rose-500/[0.04] p-2 font-mono text-[10.5px]">
          {pretty(item.error)}
        </pre>
      ) : null}
    </ToolChipShell>
  );
}
