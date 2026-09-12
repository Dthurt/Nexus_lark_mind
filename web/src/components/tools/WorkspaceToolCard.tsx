import { useMemo, useState } from "react";
import { ChevronRight } from "lucide-react";

import { FileDiffBlock } from "@/components/tools/FileDiffBlock";
import { GenericToolCard, type GenericToolCardProps } from "@/components/tools/GenericToolCard";
import { ToolStatusBadge, ToolStopButton } from "@/components/tools/ToolStatusBadge";
import { ApprovalDecisionBadge } from "@/components/chat/ApprovalDock";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { lineDiff, writeFileAsDiff } from "@/lib/lineDiff";
import { pretty } from "@/lib/pretty";
import { resolveToolStatus, statusAccentBar, statusShellClass } from "@/lib/toolStatus";
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
    if (item.error) return String(item.error).slice(0, 120);
    if (!result && (item.status === "running" || !item.status)) return "Running…";
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
        return `exit ${result?.exit_code ?? "?"} · ${String(args.command || "").slice(0, 60)}`;
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
        onInspect={onInspect}
        onOpenChange={onOpenChange}
        onStop={onStop}
      />
    );
  }

  const runStatus = resolveToolStatus(item);
  const pending = runStatus === "running";

  return (
    <Collapsible
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        item.open = next;
        onOpenChange?.(next);
      }}
      className={cn(
        "tool-card relative w-full max-w-full self-stretch overflow-hidden rounded-lg border text-sm",
        statusShellClass(runStatus),
        nested && "ml-0",
        highlighted && "ring-2 ring-amber-400/70 border-amber-400/50 shadow-[0_0_0_1px_rgba(251,191,36,0.25)]",
      )}
      data-approval-call={item.callId || undefined}
    >
      <div className={cn("absolute inset-y-0 left-0 w-0.5", statusAccentBar(runStatus))} aria-hidden />
      <div className="flex items-center gap-1 pr-1.5">
        <CollapsibleTrigger asChild>
          <button
            type="button"
            className={cn(
              "flex min-w-0 flex-1 items-center gap-1.5 py-1.5 pl-2.5 text-left hover:bg-foreground/[0.03]",
              open && !nested && "border-b border-border/40",
            )}
          >
            <ChevronRight
              className={cn("size-3.5 shrink-0 text-muted-foreground transition-transform", open && "rotate-90")}
              aria-hidden
            />
            <Badge
              variant="outline"
              className="h-5 shrink-0 border-border/60 bg-background/30 px-1.5 font-mono text-[10px] font-medium text-muted-foreground"
            >
              {badge}
            </Badge>
            <span className="min-w-0 flex-1 truncate font-mono text-xs text-foreground/90">{item.name}</span>
            <ToolStatusBadge status={runStatus} />
            <ApprovalDecisionBadge decision={(item as any).approvalDecision} />
            {mutationStats ? (
              <span
                className="inline-flex shrink-0 gap-1.5 font-mono text-[11px] tabular-nums"
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
            ) : null}
            <span className="inline-flex min-w-0 shrink-0 items-center gap-2 font-mono text-[10px] text-muted-foreground">
              <span className="min-w-0 truncate">{summary}</span>
            </span>
          </button>
        </CollapsibleTrigger>
        {pending ? <ToolStopButton onStop={() => onStop?.(item.callId)} /> : null}
      </div>
      <CollapsibleContent className="space-y-2 px-2.5 py-2">
        {toolKey === "run_shell" && args.command ? (
          <div className="space-y-1">
            <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Command</div>
            <pre className="max-h-40 overflow-auto whitespace-pre-wrap break-words rounded-md border border-border bg-background/50 p-2 font-mono text-[10.5px]">
              {args.command}
            </pre>
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
          <div className="space-y-1">
            <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Arguments</div>
            <pre className="max-h-40 overflow-auto whitespace-pre-wrap break-words rounded-md border border-border bg-background/50 p-2 font-mono text-[10.5px] text-muted-foreground">
              {pretty(item.arguments)}
            </pre>
          </div>
        ) : null}

        {item.error != null ? (
          <div className="space-y-1">
            <div className="text-[10px] uppercase tracking-wide text-destructive">Error</div>
            <pre className="max-h-40 overflow-auto whitespace-pre-wrap break-words rounded-md border border-destructive/30 bg-destructive/5 p-2 font-mono text-[10.5px]">
              {pretty(item.error)}
            </pre>
          </div>
        ) : previewLines.length ? (
          <div className="space-y-1">
            <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Preview</div>
            <pre className="max-h-[220px] overflow-auto whitespace-pre-wrap break-words rounded-md border border-border bg-background/50 p-2 font-mono text-[10.5px] text-muted-foreground">
              {previewLines.join("\n")}
            </pre>
          </div>
        ) : result && !fileChange ? (
          <div className="space-y-1">
            <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Result</div>
            <pre className="max-h-40 overflow-auto whitespace-pre-wrap break-words rounded-md border border-border bg-background/50 p-2 font-mono text-[10.5px] text-muted-foreground">
              {pretty(result)}
            </pre>
          </div>
        ) : null}

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

export default WorkspaceToolCard;
