import { useMemo, useState } from "react";

import { FileDiffBlock } from "@/components/tools/FileDiffBlock";
import { GenericToolCard, type GenericToolCardProps } from "@/components/tools/GenericToolCard";
import { ToolChipShell } from "@/components/tools/ToolChipShell";
import { lineDiff, writeFileAsDiff } from "@/lib/lineDiff";
import { pretty } from "@/lib/pretty";
import { shortToolName } from "@/lib/toolChip";
import { resolveToolStatus } from "@/lib/toolStatus";
import { cn } from "@/lib/utils";

function parseResult(raw: unknown) {
  if (raw == null) return null;
  let data: any = raw;
  if (typeof raw === "string") {
    try {
      data = JSON.parse(raw);
    } catch {
      return null;
    }
  }
  return data && typeof data === "object" ? data : null;
}

function resolveToolKey(name?: string) {
  const n = String(name || "").toLowerCase();
  if (n.includes("grep")) return "grep";
  if (n.includes("glob")) return "glob";
  if (n.includes("list_dir")) return "list_dir";
  if (n.includes("read_file")) return "read_file";
  if (n.includes("write_file")) return "write_file";
  if (n.includes("edit_file")) return "edit_file";
  if (n.includes("run_shell")) return "run_shell";
  return "other";
}

const BADGE_MAP: Record<string, string> = {
  grep: "GREP",
  glob: "GLOB",
  list_dir: "LS",
  read_file: "READ",
  write_file: "WRITE",
  edit_file: "EDIT",
  run_shell: "SHELL",
};

function PreBlock({
  children,
  tone = "default",
  maxH = "max-h-40",
}: {
  children: string;
  tone?: "default" | "error";
  maxH?: string;
}) {
  return (
    <pre
      className={cn(
        maxH,
        "overflow-auto whitespace-pre-wrap break-words rounded-md p-2 font-mono text-[10.5px]",
        tone === "error"
          ? "border border-destructive/30 bg-destructive/5"
          : "border border-border/50 bg-background/35 text-muted-foreground",
      )}
    >
      {children}
    </pre>
  );
}

export function WorkspaceToolCard({
  item,
  nested = false,
  highlighted = false,
  onInspect,
  onOpenChange,
  onStop,
}: GenericToolCardProps) {
  const result = useMemo(() => parseResult(item.result), [item.result]);
  const toolKey = resolveToolKey(item.name);
  const [open, setOpen] = useState(!!item.open);

  const badge = BADGE_MAP[toolKey] || item.badge || "TOOL";
  const args = useMemo(() => {
    let raw: any = item.arguments;
    if (typeof raw === "string") {
      try {
        raw = JSON.parse(raw);
      } catch {
        raw = {};
      }
    }
    return (raw && typeof raw === "object" ? raw : {}) as Record<string, any>;
  }, [item.arguments]);

  const fileChange = useMemo(() => {
    const path = args.path || result?.path || "";
    if (toolKey === "edit_file" && (args.old_string != null || args.new_string != null)) {
      const diff = lineDiff(args.old_string ?? "", args.new_string ?? "");
      return { path, ...diff, kind: "edit" as const };
    }
    if (toolKey === "write_file" && args.content != null) {
      const diff = writeFileAsDiff(args.content);
      return { path, ...diff, kind: "write" as const };
    }
    return null;
  }, [args, result, toolKey]);

  const summary = useMemo(() => {
    if (item.error) return String(item.error).slice(0, 100);
    if (!result && (item.status === "running" || !item.status)) return "…";
    switch (toolKey) {
      case "grep":
        return `${args.pattern || ""} · ${result?.match_count ?? (result?.matches || []).length} 处`;
      case "glob":
        return `${args.pattern || ""} · ${(result?.files || []).length} 个文件`;
      case "list_dir":
        return `${args.path || result?.path || "."} · ${(result?.entries || []).length} 项`;
      case "read_file":
        return `${args.path || result?.path || ""} · L${result?.offset || 1}+`;
      case "write_file":
      case "edit_file":
        return args.path || result?.path || "";
      case "run_shell":
        return `exit ${result?.exit_code ?? "?"} · ${String(args.command || "").slice(0, 56)}`;
      default:
        return "";
    }
  }, [args, item.error, item.status, result, toolKey]);

  const previewLines = useMemo(() => {
    if (!result) return [] as string[];
    if (toolKey === "grep") {
      return (result.matches || []).slice(0, 12).map((m: any) => `${m.path}:${m.line}: ${m.text}`);
    }
    if (toolKey === "glob") return (result.files || []).slice(0, 20);
    if (toolKey === "list_dir") {
      return (result.entries || [])
        .slice(0, 20)
        .map((e: any) => `${e.is_dir ? "📁" : "📄"} ${e.name}`);
    }
    if (toolKey === "read_file" && result.content) {
      return String(result.content).split("\n").slice(0, 16);
    }
    if (toolKey === "run_shell") {
      const out = [result.stdout, result.stderr].filter(Boolean).join("\n").trim();
      return out ? out.split("\n").slice(0, 16) : [];
    }
    return [];
  }, [result, toolKey]);

  const useRich = toolKey !== "other" && !!(result || item.arguments);
  const isFileMutation = toolKey === "write_file" || toolKey === "edit_file";
  const mutationStats =
    isFileMutation && !item.error && fileChange?.stats
      ? {
          adds: Number(fileChange.stats.adds || 0),
          dels: Number(fileChange.stats.dels || 0),
        }
      : null;

  if (!useRich) {
    return (
      <GenericToolCard
        item={item}
        nested={nested}
        highlighted={highlighted}
        onInspect={onInspect}
        onOpenChange={onOpenChange}
        onStop={onStop}
      />
    );
  }

  const runStatus = resolveToolStatus(item);
  const title = shortToolName(item.name);

  return (
    <ToolChipShell
      callId={item.callId}
      status={runStatus}
      badge={badge}
      title={title}
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
      headerExtra={
        mutationStats ? (
          <span
            className="inline-flex shrink-0 gap-1 font-mono text-[11px] tabular-nums"
            aria-label="line changes"
          >
            {mutationStats.adds ? (
              <span className="font-semibold text-emerald-400">+{mutationStats.adds}</span>
            ) : null}
            {mutationStats.dels ? (
              <span className="font-semibold text-rose-400">−{mutationStats.dels}</span>
            ) : null}
            {!mutationStats.adds && !mutationStats.dels ? (
              <span className="text-muted-foreground">±0</span>
            ) : null}
          </span>
        ) : null
      }
    >
      {toolKey === "run_shell" && args.command ? (
        <div className="space-y-0.5">
          <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Command</div>
          <PreBlock>{args.command}</PreBlock>
        </div>
      ) : null}

      {fileChange && !item.error ? (
        <FileDiffBlock
          path={fileChange.path}
          rows={fileChange.rows}
          stats={fileChange.stats}
          defaultOpen
        />
      ) : item.arguments &&
        !isFileMutation &&
        !["grep", "glob", "list_dir", "read_file"].includes(toolKey) ? (
        <div className="space-y-0.5">
          <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Arguments</div>
          <PreBlock>{pretty(item.arguments)}</PreBlock>
        </div>
      ) : null}

      {item.error != null ? (
        <div className="space-y-0.5">
          <div className="text-[10px] uppercase tracking-wide text-destructive">Error</div>
          <PreBlock tone="error">{pretty(item.error)}</PreBlock>
        </div>
      ) : previewLines.length ? (
        <div className="space-y-0.5">
          <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Preview</div>
          <PreBlock maxH="max-h-[220px]">{previewLines.join("\n")}</PreBlock>
        </div>
      ) : result && !fileChange ? (
        <div className="space-y-0.5">
          <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Result</div>
          <PreBlock>{pretty(result)}</PreBlock>
        </div>
      ) : null}
    </ToolChipShell>
  );
}

export default WorkspaceToolCard;
