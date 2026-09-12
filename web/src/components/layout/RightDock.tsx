import { useCallback, useMemo, useRef, useState, type MouseEvent as ReactMouseEvent } from "react";
import { RefreshCw, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { HoverCard, HoverCardContent, HoverCardTrigger } from "@/components/ui/hover-card";
import { Progress } from "@/components/ui/progress";
import { Switch } from "@/components/ui/switch";
import { TeamsPanel } from "@/components/layout/TeamsPanel";
import { DeliveryPanel } from "@/components/layout/DeliveryPanel";
import type { DockPane, useRightDock } from "@/hooks/useRightDock";
import type { DeliveryArtifactApi } from "@/hooks/useDeliveryArtifact";
import {
  estimateContextOccupancy,
  formatCompactTokens,
  formatSharePercent,
} from "@/lib/contextEstimate";
import { formatTokenCount } from "@/lib/pricing";
import { pretty } from "@/lib/pretty";
import type { Plugin, Tool, Usage } from "@/types/api";
import { cn } from "@/lib/utils";

export type ActivityItem = {
  id?: string;
  kind: string;
  name?: string;
  detail?: unknown;
  at?: number;
  callId?: string;
};

export type RightDockController = ReturnType<typeof useRightDock>;

export type RightDockProps = {
  dock: RightDockController;
  plugins?: Plugin[];
  tools?: Tool[];
  activity?: ActivityItem[];
  /** Running / recent tool & subagent cards from the chat timeline. */
  jobs?: any[];
  usage?: Usage;
  pluginError?: string | null;
  reloading?: boolean;
  highlightActivityId?: string | null;
  inspectorPayload?: unknown;
  /** Context composition inputs (same as composer meter). */
  contextItems?: any[];
  modelName?: string;
  cwd?: string;
  /** local | ssh — Delivery disk write only for local */
  workspaceKind?: string;
  workspaceTitle?: string;
  draft?: string;
  /** Team mailbox / DAG (defaults to session id). */
  teamId?: string;
  /** Plan→Diagram→Changes delivery artifact. */
  delivery?: DeliveryArtifactApi | null;
  sessionId?: string;
  onTogglePlugin?: (pluginId: string, enabled: boolean) => void | Promise<void>;
  onReload?: () => void | Promise<void>;
  onReloadOne?: (pluginId: string) => void | Promise<void>;
  onRetryPlugin?: (pluginId: string) => void | Promise<void>;
  onViewSchema?: (tool: Tool) => void;
  onSavePluginConfig?: (
    pluginId: string,
    values: Record<string, string>,
  ) => void | Promise<void>;
  onInspectJob?: (activityId: string) => void;
  onStopJob?: (callId?: string) => void;
  className?: string;
};

function activeKind(pane: DockPane): string | null {
  const tab = pane.tabs.find((t) => t.id === pane.activeId);
  return tab?.kind || null;
}

function cacheHitRate(usage: Usage): string {
  const prompt = Number(usage.prompt_tokens || 0);
  const cached = Number(usage.cached_tokens || 0);
  if (prompt > 0 && cached > 0) return `${((cached / prompt) * 100).toFixed(1)}%`;
  return "0%";
}

export function RightDock({
  dock,
  plugins = [],
  tools = [],
  activity = [],
  jobs = [],
  usage = {},
  pluginError,
  reloading = false,
  highlightActivityId,
  inspectorPayload,
  contextItems = [],
  modelName = "",
  cwd = "",
  workspaceKind = "local",
  workspaceTitle = "",
  draft = "",
  teamId = "",
  delivery = null,
  sessionId = "",
  onTogglePlugin,
  onReload,
  onReloadOne,
  onRetryPlugin,
  onViewSchema,
  onInspectJob,
  onStopJob,
  className,
}: RightDockProps) {
  const [toggling, setToggling] = useState<Record<string, boolean>>({});
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [schemaTool, setSchemaTool] = useState<Tool | null>(null);
  const [dragging, setDragging] = useState(false);
  const panesHostRef = useRef<HTMLDivElement>(null);

  const panes = dock.visiblePanes;
  const state = dock.state;

  const showSchema = useCallback(
    (tool: Tool) => {
      setSchemaTool(tool);
      onViewSchema?.(tool);
    },
    [onViewSchema],
  );

  const onToggle = useCallback(
    (plugin: Plugin, enabled: boolean) => {
      const id = plugin.plugin_id;
      setToggling((m) => ({ ...m, [id]: true }));
      void Promise.resolve(onTogglePlugin?.(id, enabled)).finally(() => {
        setTimeout(() => {
          setToggling((m) => ({ ...m, [id]: false }));
        }, 400);
      });
    },
    [onTogglePlugin],
  );

  const startDrag = useCallback(
    (e: ReactMouseEvent) => {
      e.preventDefault();
      setDragging(true);
      const host = panesHostRef.current;
      const onMove = (ev: MouseEvent) => {
        if (!host) return;
        const rect = host.getBoundingClientRect();
        const y = (ev.clientY - rect.top) / rect.height;
        dock.setRatio(y || state.ratio);
      };
      const onUp = () => {
        setDragging(false);
        window.removeEventListener("mousemove", onMove);
        window.removeEventListener("mouseup", onUp);
      };
      window.addEventListener("mousemove", onMove);
      window.addEventListener("mouseup", onUp);
    },
    [dock, state.ratio],
  );

  const totalTokens = useMemo(() => {
    if (usage.total_tokens != null) return Number(usage.total_tokens);
    return Number(usage.prompt_tokens || 0) + Number(usage.completion_tokens || 0);
  }, [usage]);

  return (
    <aside
      className={cn(
        "nlm-rail relative flex h-full min-h-0 w-[var(--rail-w)] flex-col overflow-hidden border-l border-border bg-card/70 backdrop-blur-md",
        className,
      )}
      aria-label="扩展停靠栏"
    >
      <div className="flex shrink-0 items-center justify-between border-b border-border px-2.5 py-2">
        <span className="text-[10.5px] uppercase tracking-[0.06em] text-muted-foreground">
          Dock
        </span>
        <div className="flex gap-1">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-7 px-2 text-[11px]"
            title={state.split ? "合并面板" : "拆分检查器"}
            onClick={() =>
              state.split ? dock.disableSplit() : dock.enableSplit("inspector")
            }
          >
            {state.split ? "合并" : "拆分"}
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-7 px-2"
            title="重载插件"
            disabled={reloading}
            onClick={() => void onReload?.()}
          >
            <RefreshCw className={cn("size-3.5", reloading && "animate-spin")} />
          </Button>
        </div>
      </div>

      <div
        ref={panesHostRef}
        className={cn("flex min-h-0 flex-1 flex-col overflow-hidden", state.split && "gap-0")}
      >
        {panes.map((pane, pi) => {
          const kind = activeKind(pane);
          return (
            <div
              key={pane.id}
              className="relative flex min-h-0 flex-1 flex-col overflow-hidden"
              style={
                state.split && pi === 0
                  ? { flex: `0 0 ${state.ratio * 100}%` }
                  : state.split
                    ? { flex: "1 1 auto" }
                    : undefined
              }
            >
              <div className="flex shrink-0 flex-wrap gap-0.5 border-b border-border px-2 pt-1.5">
                {pane.tabs.map((tab) => (
                  <button
                    key={tab.id}
                    type="button"
                    className={cn(
                      "rounded-t-md px-2 py-1.5 text-[10.5px] text-muted-foreground",
                      pane.activeId === tab.id &&
                        "bg-primary/15 text-foreground shadow-[inset_0_-2px_0_hsl(var(--primary))]",
                    )}
                    onClick={() => dock.focusTab(pane.id, tab.id)}
                  >
                    {tab.title}
                    {(pane.id === "aux" || tab.kind === "inspector") && (
                      <span
                        className="ml-1 opacity-60 hover:opacity-100"
                        onClick={(e) => {
                          e.stopPropagation();
                          dock.closeTab(pane.id, tab.id);
                        }}
                      >
                        ×
                      </span>
                    )}
                  </button>
                ))}
              </div>

              <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
                {kind === "plugins" && (
                  <PluginsPanel
                    plugins={plugins}
                    pluginError={pluginError}
                    expanded={expanded}
                    toggling={toggling}
                    onExpand={(id) =>
                      setExpanded((m) => ({ ...m, [id]: !m[id] }))
                    }
                    onToggle={onToggle}
                    onReloadOne={onReloadOne}
                    onRetryPlugin={onRetryPlugin}
                    onShowSchema={showSchema}
                  />
                )}
                {kind === "teams" && <TeamsPanel teamId={teamId} />}
                {kind === "delivery" && delivery ? (
                  <DeliveryPanel
                    delivery={delivery}
                    sessionId={sessionId || teamId}
                    cwd={cwd}
                    workspaceKind={workspaceKind}
                  />
                ) : null}
                {kind === "jobs" && (
                  <JobsPanel
                    jobs={jobs}
                    onInspect={onInspectJob}
                    onStop={onStopJob}
                  />
                )}
                {kind === "activity" && (
                  <ActivityPanel
                    activity={activity}
                    highlightActivityId={highlightActivityId}
                    onOpen={(item) => dock.openInspector(item)}
                  />
                )}
                {kind === "usage" && (
                  <UsagePanel
                    usage={usage}
                    totalTokens={totalTokens}
                    tools={tools}
                    contextItems={contextItems}
                    modelName={modelName}
                    cwd={cwd}
                    workspaceTitle={workspaceTitle}
                    draft={draft}
                    onShowSchema={showSchema}
                  />
                )}
                {kind === "inspector" && (
                  <InspectorPanel
                    payload={
                      inspectorPayload ??
                      pane.tabs.find((t) => t.id === pane.activeId)?.params ?? {
                        tip: "从 Trajectory 或活动点击一行",
                      }
                    }
                  />
                )}
              </div>

              {state.split && pi === 0 ? (
                <div
                  className={cn(
                    "h-1.5 shrink-0 cursor-row-resize border-y border-border bg-foreground/[0.04] hover:bg-primary/20",
                    dragging && "bg-primary/20",
                  )}
                  onMouseDown={startDrag}
                />
              ) : null}
            </div>
          );
        })}
      </div>

      {schemaTool ? (
        <div
          className="absolute inset-0 z-[5] flex items-end bg-black/45 p-2.5"
          onClick={() => setSchemaTool(null)}
        >
          <div
            className="max-h-[70%] w-full overflow-auto rounded-[10px] border border-border bg-card p-2.5"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-1.5 flex items-center justify-between">
              <strong className="text-xs">{schemaTool.name}</strong>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-7 px-2"
                onClick={() => setSchemaTool(null)}
              >
                <X className="size-3.5" />
                关闭
              </Button>
            </div>
            <pre className="m-0 whitespace-pre-wrap font-mono text-[10.5px]">
              {pretty(schemaTool.inputSchema || schemaTool.parameters || {})}
            </pre>
          </div>
        </div>
      ) : null}
    </aside>
  );
}

function PluginsPanel({
  plugins,
  pluginError,
  expanded,
  toggling,
  onExpand,
  onToggle,
  onReloadOne,
  onRetryPlugin,
  onShowSchema,
}: {
  plugins: Plugin[];
  pluginError?: string | null;
  expanded: Record<string, boolean>;
  toggling: Record<string, boolean>;
  onExpand: (id: string) => void;
  onToggle: (plugin: Plugin, enabled: boolean) => void;
  onReloadOne?: (pluginId: string) => void | Promise<void>;
  onRetryPlugin?: (pluginId: string) => void | Promise<void>;
  onShowSchema: (tool: Tool) => void;
}) {
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto overscroll-contain p-2.5">
      <p className="m-0 text-[10.5px] text-muted-foreground">
        启停写入 prefs；仅 ready 进入模型工具列表
      </p>
      {pluginError ? (
        <p className="m-0 text-[10.5px] text-destructive">{pluginError}</p>
      ) : null}
      {!pluginError && plugins.length === 0 ? (
        <p className="m-0 text-[10.5px] text-muted-foreground">暂无插件</p>
      ) : null}
      <div className="flex flex-col gap-1.5">
        {plugins.map((p) => {
          const open = !!expanded[p.plugin_id];
          return (
            <div
              key={p.plugin_id}
              className={cn(
                "rounded-lg border border-border bg-foreground/[0.03] px-2.5 py-2",
                p.state === "error" && "border-destructive/40",
              )}
            >
              <div className="flex items-start gap-2">
                <button
                  type="button"
                  className="min-w-0 flex-1 text-left"
                  onClick={() => onExpand(p.plugin_id)}
                >
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs font-semibold">{p.name || p.plugin_id}</span>
                    <Badge
                      variant="outline"
                      className={cn(
                        "h-4 px-1 font-mono text-[10px] uppercase",
                        p.state === "ready" && "border-teal/40 text-teal",
                        p.state === "error" && "border-destructive/50 text-destructive",
                      )}
                    >
                      {p.state || "—"}
                    </Badge>
                  </div>
                  <div className="font-mono text-[10.5px] text-muted-foreground">
                    {p.plugin_id} · {p.kind}
                  </div>
                </button>
                <div className="flex items-center gap-1">
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="size-7"
                    onClick={() => void onReloadOne?.(p.plugin_id)}
                  >
                    <RefreshCw className="size-3" />
                  </Button>
                  <Switch
                    checked={!!p.enabled}
                    disabled={!!toggling[p.plugin_id]}
                    onCheckedChange={(v) => onToggle(p, v)}
                  />
                </div>
              </div>
              {p.last_error && p.state === "error" ? (
                <div className="mt-1.5 text-[10.5px] text-destructive">{p.last_error}</div>
              ) : null}
              {p.state === "error" ? (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="mt-1 h-7 px-2 text-[11px]"
                  onClick={() => void onRetryPlugin?.(p.plugin_id)}
                >
                  重试启用
                </Button>
              ) : null}
              {(p.config_hints || []).map((h, i) => (
                <div key={i} className="mt-1 text-[10.5px] text-[hsl(var(--tool))]">
                  {h}
                </div>
              ))}
              {open ? (
                <div className="mt-2 flex flex-wrap gap-1">
                  {(p.tools || []).length ? (
                    (p.tools || []).map((t) => (
                      <button
                        key={t.name}
                        type="button"
                        onClick={() => onShowSchema(t)}
                      >
                        <Badge
                          variant="outline"
                          className={cn(
                            "font-mono text-[10px]",
                            p.state === "ready" && "border-teal/35 text-teal",
                          )}
                        >
                          {t.name}
                        </Badge>
                      </button>
                    ))
                  ) : (
                    <Badge variant="outline" className="text-[10px]">
                      {p.enabled ? "no tools" : "已禁用"}
                    </Badge>
                  )}
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function JobsPanel({
  jobs,
  onInspect,
  onStop,
}: {
  jobs: any[];
  onInspect?: (activityId: string) => void;
  onStop?: (callId?: string) => void;
}) {
  const running = jobs.filter((j) => {
    const s = String(j?.status || "").toLowerCase();
    return s === "running" || s === "" || s == null;
  });
  const recent = jobs
    .filter((j) => !running.includes(j))
    .slice(-12)
    .reverse();

  function shortName(name?: string) {
    const raw = String(name || "tool");
    return raw.replace(/^builtin_workspace_/, "").replace(/^cli_/, "").split(".").pop();
  }

  function row(j: any) {
    const st = String(j?.status || "done").toLowerCase() || "done";
    const title =
      j?.kind === "subagent"
        ? j?.label || j?.subagentId || "subagent"
        : shortName(j?.name) || "tool";
    const runningRow = st === "running";
    return (
      <div
        key={j.id}
        className={cn(
          "flex items-start justify-between gap-2 rounded-lg border px-2 py-1.5 text-[11px]",
          runningRow
            ? "border-sky-500/35 bg-sky-500/10"
            : "border-border/60 bg-muted/20",
        )}
      >
        <button
          type="button"
          className="min-w-0 flex-1 text-left"
          onClick={() => onInspect?.(j.activityId || j.id)}
        >
          <div className="truncate font-medium text-foreground">{title}</div>
          <div className="text-muted-foreground">
            {j.kind === "subagent" ? "子代理" : "工具"} · {st}
          </div>
        </button>
        {runningRow ? (
          <Button
            type="button"
            size="sm"
            variant="ghost"
            className="h-6 shrink-0 px-2 text-[10px]"
            onClick={() => onStop?.(j.callId || j.id)}
          >
            停止
          </Button>
        ) : null}
      </div>
    );
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto overscroll-contain p-2.5">
      <p className="m-0 text-[10.5px] text-muted-foreground">
        长 shell / 子代理后台任务（来自当前会话时间线）
      </p>
      {!jobs.length ? (
        <p className="m-0 text-[10.5px] text-muted-foreground">暂无 Jobs</p>
      ) : (
        <>
          {running.length ? (
            <div className="flex flex-col gap-1.5">
              <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
                运行中 · {running.length}
              </div>
              {running.map(row)}
            </div>
          ) : null}
          {recent.length ? (
            <div className="flex flex-col gap-1.5">
              <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
                最近
              </div>
              {recent.map(row)}
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}

function ActivityPanel({
  activity,
  highlightActivityId,
  onOpen,
}: {
  activity: ActivityItem[];
  highlightActivityId?: string | null;
  onOpen: (item: ActivityItem) => void;
}) {
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto overscroll-contain p-2.5">
      <p className="m-0 text-[10.5px] text-muted-foreground">本会话工具活动</p>
      {!activity.length ? (
        <p className="m-0 text-[10.5px] text-muted-foreground">暂无工具活动</p>
      ) : (
        <div className="flex flex-col gap-1.5">
          {activity.map((item) => (
            <button
              key={item.id || item.at}
              type="button"
              className={cn(
                "rounded-lg border border-[hsl(var(--tool)/0.22)] bg-[hsl(var(--tool)/0.06)] px-2 py-1.5 text-left text-[10.5px]",
                item.id &&
                  item.id === highlightActivityId &&
                  "outline outline-1 outline-primary/55 bg-primary/15",
              )}
              onClick={() => onOpen(item)}
            >
              <span className="mr-1.5 font-mono text-[hsl(var(--tool))]">{item.kind}</span>
              <span className="font-mono">{item.name}</span>
              <pre className="mt-1 max-h-[90px] overflow-auto whitespace-pre-wrap break-words text-muted-foreground">
                {pretty(item.detail)}
              </pre>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function UsagePanel({
  usage,
  totalTokens,
  tools,
  contextItems = [],
  modelName = "",
  cwd = "",
  workspaceTitle = "",
  draft = "",
  onShowSchema,
}: {
  usage: Usage;
  totalTokens: number;
  tools: Tool[];
  contextItems?: any[];
  modelName?: string;
  cwd?: string;
  workspaceTitle?: string;
  draft?: string;
  onShowSchema: (tool: Tool) => void;
}) {
  const lastPromptTokens = useMemo(() => {
    for (let i = contextItems.length - 1; i >= 0; i -= 1) {
      const it = contextItems[i];
      if (it?.kind === "msg" && it.role === "assistant" && it.usage?.prompt_tokens) {
        return Number(it.usage.prompt_tokens) || 0;
      }
    }
    return 0;
  }, [contextItems]);

  const occupancy = useMemo(
    () =>
      estimateContextOccupancy({
        items: contextItems,
        tools,
        modelName,
        cwd,
        workspaceTitle,
        lastPromptTokens,
        draft,
      }),
    [contextItems, tools, modelName, cwd, workspaceTitle, lastPromptTokens, draft],
  );

  const compositionRows = useMemo(() => {
    const b = occupancy.breakdown;
    return [
      {
        key: "system" as const,
        label: "系统提示",
        tokens: b.systemTokens,
        share: occupancy.windowShares.system,
        usedShare: occupancy.usedShares.system,
        color: "bg-[#7aa2c8]",
      },
      {
        key: "tools" as const,
        label: "工具定义",
        tokens: b.toolsTokens,
        share: occupancy.windowShares.tools,
        usedShare: occupancy.usedShares.tools,
        color: "bg-[#a78bfa]",
      },
      {
        key: "messages" as const,
        label: "对话消息",
        tokens: b.messageTokens,
        share: occupancy.windowShares.messages,
        usedShare: occupancy.usedShares.messages,
        color: "bg-[#3a9cf0]",
      },
      {
        key: "free" as const,
        label: "剩余可用",
        tokens: b.freeTokens,
        share: occupancy.windowShares.free,
        usedShare: 0,
        color: "bg-foreground/15",
      },
    ];
  }, [occupancy]);

  const prompt = Number(usage.prompt_tokens || 0);
  const completion = Number(usage.completion_tokens || 0);
  const cached = Number(usage.cached_tokens || 0);
  const ioTotal = Math.max(1, prompt + completion);
  const ioRows = [
    {
      key: "prompt",
      label: "输入",
      value: prompt,
      width: (prompt / ioTotal) * 100,
      color: "bg-[#3a9cf0]",
    },
    {
      key: "completion",
      label: "输出",
      value: completion,
      width: (completion / ioTotal) * 100,
      color: "bg-[#2bb8a0]",
    },
  ];
  const cacheShare = prompt > 0 ? cached / prompt : 0;

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto overscroll-contain p-2.5">
      <div className="mb-1 rounded-lg border border-border bg-foreground/[0.03] p-2.5">
        <div className="mb-2 flex items-center justify-between gap-2 text-[10.5px] uppercase tracking-wide text-muted-foreground">
          <span>上下文构成</span>
          <span className="normal-case tracking-normal font-mono text-foreground">
            {occupancy.percent}% · ~{formatCompactTokens(occupancy.usedTokens)} /{" "}
            {formatCompactTokens(occupancy.contextWindow)}
          </span>
        </div>
        <div className="mb-2 flex h-2 overflow-hidden rounded-full bg-muted" aria-hidden>
          {compositionRows
            .filter((r) => r.key !== "free" && r.tokens > 0)
            .map((row) => (
              <div
                key={row.key}
                className={cn("h-full min-w-[2px]", row.color)}
                style={{
                  width: `${Math.max(occupancy.percent * row.usedShare, 0.4)}%`,
                }}
                title={row.label}
              />
            ))}
        </div>
        <div className="space-y-1">
          {compositionRows.map((row) => (
            <div key={row.key} className="flex items-center justify-between gap-2 text-xs">
              <span className="inline-flex min-w-0 items-center gap-1.5 text-muted-foreground">
                <span className={cn("size-2 shrink-0 rounded-sm", row.color)} aria-hidden />
                <span className="truncate">{row.label}</span>
              </span>
              <span className="shrink-0 tabular-nums">
                <span className="mr-2 text-muted-foreground">{formatSharePercent(row.share)}</span>
                <strong className="font-mono font-medium text-foreground">
                  ~{formatCompactTokens(row.tokens)}
                </strong>
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className="mb-1 rounded-lg border border-border bg-foreground/[0.03] p-2.5">
        <div className="mb-2 flex items-center justify-between gap-2 text-[10.5px] uppercase tracking-wide text-muted-foreground">
          <span>会话累计</span>
          <HoverCard>
            <HoverCardTrigger asChild>
              <button type="button" className="normal-case tracking-normal text-primary/80 hover:underline">
                详情
              </button>
            </HoverCardTrigger>
            <HoverCardContent className="w-56 text-xs">
              <p className="m-0 font-medium text-foreground">Token 分布</p>
              <p className="mt-1 m-0 text-muted-foreground">
                输入 {formatTokenCount(prompt)} · 输出 {formatTokenCount(completion)} · 缓存{" "}
                {formatTokenCount(cached)}
              </p>
            </HoverCardContent>
          </HoverCard>
        </div>

        <div className="mb-1.5 flex justify-between text-[10.5px] text-muted-foreground">
          <span>输入 / 输出占比</span>
          <span className="font-mono">{formatTokenCount(totalTokens)}</span>
        </div>
        <div className="mb-2 flex h-2 overflow-hidden rounded-full bg-muted" aria-hidden>
          {ioRows
            .filter((r) => r.value > 0)
            .map((row) => (
              <div
                key={row.key}
                className={cn("h-full min-w-[2px]", row.color)}
                style={{ width: `${Math.max(row.width, 0.5)}%` }}
                title={`${row.label} ${row.value}`}
              />
            ))}
        </div>
        {ioRows.map((row) => (
          <div key={row.key} className="flex items-center justify-between gap-2 py-0.5 text-xs">
            <span className="inline-flex items-center gap-1.5 text-muted-foreground">
              <span className={cn("size-2 rounded-sm", row.color)} aria-hidden />
              {row.label}
            </span>
            <span className="tabular-nums">
              <span className="mr-2 text-muted-foreground">
                {formatSharePercent(row.value / ioTotal)}
              </span>
              <strong className="font-mono font-medium">{formatTokenCount(row.value)}</strong>
            </span>
          </div>
        ))}
        <UsageRow label="合计" value={formatTokenCount(totalTokens)} />
        <div className="mt-1.5 flex items-center justify-between gap-2 py-0.5 text-xs">
          <span className="text-muted-foreground">缓存命中</span>
          <span className="tabular-nums">
            <span className="mr-2 text-muted-foreground">{formatSharePercent(cacheShare)}</span>
            <strong className="font-mono font-medium">{formatTokenCount(cached)}</strong>
          </span>
        </div>
        <div className="mt-1.5">
          <div className="mb-1 flex justify-between text-[10.5px] text-muted-foreground">
            <span>缓存命中率</span>
            <span className="font-mono">{cacheHitRate(usage)}</span>
          </div>
          <Progress value={Math.min(100, cacheShare * 100)} />
        </div>
        <p className="mt-2 text-[10.5px] text-muted-foreground">
          {usage.estimated
            ? "含估算值（接口未返回 usage 时按约 4 字/token）。"
            : "优先使用接口返回的 usage；上下文构成为启发式估算。"}
        </p>
      </div>
      <p className="m-0 text-[10.5px] text-muted-foreground">已启用工具 · {tools.length}</p>
      <div className="flex flex-col gap-1.5">
        {tools.map((t) => (
          <button
            key={`${t.openai_name || t.name}-${t.plugin_id || ""}`}
            type="button"
            className="flex w-full flex-col gap-0.5 rounded-md border border-border bg-foreground/[0.02] px-2 py-1.5 text-left text-[10.5px] hover:border-primary/35"
            onClick={() => onShowSchema(t)}
          >
            <div className="flex justify-between gap-2">
              <span className="font-mono">{t.name}</span>
              <span className="text-muted-foreground">{t.plugin_id}</span>
            </div>
            {t.description ? (
              <div className="text-muted-foreground">{t.description}</div>
            ) : null}
          </button>
        ))}
        {!tools.length ? (
          <p className="m-0 text-[10.5px] text-muted-foreground">当前无已启用工具</p>
        ) : null}
      </div>
    </div>
  );
}

function UsageRow({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex justify-between py-0.5 text-xs">
      <span className="text-muted-foreground">{label}</span>
      <strong className="font-mono font-medium">{value}</strong>
    </div>
  );
}

function InspectorPanel({ payload }: { payload: unknown }) {
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto overscroll-contain p-2.5">
      <p className="m-0 text-[10.5px] text-muted-foreground">
        检查器 · Trajectory / 活动详情
      </p>
      <pre className="m-0 max-h-full overflow-auto whitespace-pre-wrap break-words rounded-lg border border-border bg-background/60 p-2 font-mono text-[10.5px]">
        {pretty(payload)}
      </pre>
    </div>
  );
}

export default RightDock;
