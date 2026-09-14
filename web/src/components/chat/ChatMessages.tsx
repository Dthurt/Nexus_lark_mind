import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
  type ReactNode,
  type UIEvent,
} from "react";
import { AnimatePresence, motion } from "motion/react";

import { AskUserForm } from "@/components/chat/AskUserForm";
import { ChatFileCard } from "@/components/chat/ChatFileCard";
import { MessageBubble } from "@/components/chat/MessageBubble";
import { PlanReviewCard } from "@/components/chat/PlanReviewCard";
import { SubagentCard } from "@/components/chat/SubagentCard";
import { TodoListCard } from "@/components/chat/TodoListCard";
import { ToolCard } from "@/components/chat/ToolCard";
import { ToolCallGroup } from "@/components/chat/ToolCallGroup";
import { TurnProcessFold } from "@/components/chat/TurnProcessFold";
import { NlmLogo } from "@/components/brand/Logos";
import "@/components/tools/registerBuiltinTools";
import { WorkspacePicker } from "@/components/workspace/WorkspacePicker";
import type { TimelineItem } from "@/hooks/useChatTimeline";
import {
  timelineItemMotion,
  timelineItemMotionReduced,
  usePrefersReducedMotion,
} from "@/lib/motion";
import type { Workspace } from "@/types/api";
import { cn } from "@/lib/utils";

/** Initial visible timeline blocks; older ones load on demand (Wave C). */
const WINDOW_STEP = 60;

export type ChatMessagesProps = {
  items?: TimelineItem[];
  /** When this changes, scroll is forced to the bottom. */
  sessionId?: string | null;
  showWorkspacePicker?: boolean;
  modelProvider?: string;
  modelName?: string;
  experienceTier?: "fast" | "balanced" | "high" | string;
  onInspectTool?: (activityId: string) => void;
  onStopTool?: (callId?: string) => void;
  onPickWorkspace?: (meta: Workspace) => void;
  onResolveApproval?: (ev: {
    item: TimelineItem;
    action: string;
  }) => void;
  onResolveAsk?: (ev: {
    item: TimelineItem;
    action: string;
    answers?: Record<string, unknown>;
  }) => void;
  onResolvePlanReview?: (ev: {
    item: TimelineItem;
    action: string;
    feedback?: string;
  }) => void;
  onAcceptPlan?: (item: TimelineItem) => void;
  /** Highlight the tool card awaiting ApprovalDock decision. */
  highlightCallId?: string | null;
  className?: string;
};

export type ChatMessagesHandle = {
  el: HTMLDivElement | null;
  scrollBottom: () => void;
};

type Block =
  | { kind: "msg" | "approval" | "ask" | "todos" | "plan_review" | "subagent" | "file"; id: string; item: TimelineItem }
  | { kind: "tools"; id: string; tools: TimelineItem[] }
  | {
      kind: "turn_process";
      id: string;
      summary: string;
      reasoning: string;
      tools: TimelineItem[];
      subagents: TimelineItem[];
      botId: string;
    };

function nearBottom(el: HTMLElement, threshold = 80) {
  return el.scrollHeight - el.scrollTop - el.clientHeight < threshold;
}

function buildBlocks(items: TimelineItem[]): Block[] {
  const out: Block[] = [];
  // Precompute fold groups keyed by assistant bubble id.
  const foldBuckets = new Map<
    string,
    { tools: TimelineItem[]; subagents: TimelineItem[] }
  >();
  for (const item of items || []) {
    const botId = String(item.foldInto || "");
    if (!botId) continue;
    if (item.kind !== "tool" && item.kind !== "subagent") continue;
    let bucket = foldBuckets.get(botId);
    if (!bucket) {
      bucket = { tools: [], subagents: [] };
      foldBuckets.set(botId, bucket);
    }
    if (item.kind === "tool") bucket.tools.push(item);
    else bucket.subagents.push(item);
  }

  for (const item of items || []) {
    if (item.foldInto) {
      // Emitted as part of turn_process when we hit the assistant bubble.
      continue;
    }
    if (
      item.kind === "approval" ||
      item.kind === "ask" ||
      item.kind === "todos" ||
      item.kind === "plan_review"
    ) {
      if (item.kind === "approval") continue;
      out.push({ kind: item.kind, id: item.id, item });
      continue;
    }
    if (item.kind === "tool") {
      const last = out[out.length - 1];
      if (last && last.kind === "tools") {
        last.tools.push(item);
      } else {
        out.push({ kind: "tools", id: `tools-${item.id}`, tools: [item] });
      }
      continue;
    }
    if (item.kind === "file") {
      out.push({ kind: "file", id: item.id, item });
      continue;
    }
    if (item.kind === "subagent") {
      out.push({ kind: "subagent", id: item.id, item });
      continue;
    }
    if (
      item.kind === "msg" &&
      item.role === "assistant" &&
      !(item.content || "").trim() &&
      !item.activity &&
      !item.streaming &&
      !item.live &&
      !item.planReady
    ) {
      continue;
    }
    if (item.kind === "msg" && item.role === "assistant" && item.processFold && !item.streaming && !item.live) {
      const bucket = foldBuckets.get(item.id) || { tools: [], subagents: [] };
      const hasThinking = !!(item.reasoning || "").trim();
      if (hasThinking || bucket.tools.length || bucket.subagents.length) {
        out.push({
          kind: "turn_process",
          id: `proc-${item.id}`,
          summary: String(item.processFold.summary || "本回合过程"),
          reasoning: String(item.reasoning || ""),
          tools: bucket.tools,
          subagents: bucket.subagents,
          botId: item.id,
        });
      }
      out.push({ kind: "msg", id: item.id, item: { ...item, hideReasoning: true } });
      continue;
    }
    out.push({ kind: "msg", id: item.id, item });
  }
  return out;
}

export const ChatMessages = forwardRef<ChatMessagesHandle, ChatMessagesProps>(
  function ChatMessages(
    {
      items = [],
      sessionId = null,
      showWorkspacePicker = false,
      modelProvider = "",
      modelName = "",
      experienceTier = "balanced",
      onInspectTool,
      onStopTool,
      onPickWorkspace,
      onResolveApproval,
      onResolveAsk,
      onResolvePlanReview,
      onAcceptPlan,
      highlightCallId = null,
      className,
    },
    ref,
  ) {
    const scrollerRef = useRef<HTMLDivElement>(null);
    const followTailRef = useRef(true);
    const [atBottom, setAtBottom] = useState(true);
    const reducedMotion = usePrefersReducedMotion();
    const itemMotion = reducedMotion ? timelineItemMotionReduced : timelineItemMotion;
    const [windowSize, setWindowSize] = useState(WINDOW_STEP);
    const hasWorkspace = !showWorkspacePicker;
    const hasModel = !!(modelProvider || "").trim() && !!(modelName || "").trim();

    useImperativeHandle(ref, () => ({
      get el() {
        return scrollerRef.current;
      },
      scrollBottom() {
        followTailRef.current = true;
        const el = scrollerRef.current;
        if (el) el.scrollTop = el.scrollHeight;
      },
    }));

    const allBlocks = useMemo(() => buildBlocks(items), [items]);

    useEffect(() => {
      if (allBlocks.length === 0) {
        setWindowSize(WINDOW_STEP);
      }
    }, [allBlocks.length]);

    useEffect(() => {
      followTailRef.current = true;
      setAtBottom(true);
      requestAnimationFrame(() => {
        const el = scrollerRef.current;
        if (el) el.scrollTop = el.scrollHeight;
      });
    }, [sessionId]);

    const hiddenCount = Math.max(0, allBlocks.length - windowSize);
    const blocks = useMemo(
      () => (hiddenCount > 0 ? allBlocks.slice(hiddenCount) : allBlocks),
      [allBlocks, hiddenCount],
    );

    const loadEarlier = useCallback(() => {
      const el = scrollerRef.current;
      const prevHeight = el?.scrollHeight ?? 0;
      const prevTop = el?.scrollTop ?? 0;
      followTailRef.current = false;
      setWindowSize((n) => Math.min(allBlocks.length, n + WINDOW_STEP));
      requestAnimationFrame(() => {
        if (!el) return;
        el.scrollTop = el.scrollHeight - prevHeight + prevTop;
      });
    }, [allBlocks.length]);

    const maybeStickBottom = useCallback(() => {
      if (!followTailRef.current) return;
      requestAnimationFrame(() => {
        const el = scrollerRef.current;
        if (el) el.scrollTop = el.scrollHeight;
      });
    }, []);

    const stickKey = useMemo(() => {
      const last = items[items.length - 1];
      if (!last) return "";
      // Prefer length over full text so React effect deps stay cheap while streaming.
      if (last.kind === "msg") {
        return `${items.length}|${(last.content || "").length}|${(last.reasoning || "").length}|${last.streaming ? 1 : 0}`;
      }
      if (last.kind === "subagent")
        return `${items.length}|${(last.streamText || "").length}|${last.status || ""}`;
      if (last.kind === "tool") return `${items.length}|${last.status || ""}|${last.open ? 1 : 0}`;
      return `${items.length}|${last.id || ""}`;
    }, [items]);

    useEffect(() => {
      if (!highlightCallId) return;
      requestAnimationFrame(() => {
        const el = scrollerRef.current?.querySelector(
          `[data-approval-call="${CSS.escape(highlightCallId)}"]`,
        ) as HTMLElement | null;
        el?.scrollIntoView({ block: "nearest", behavior: "smooth" });
      });
    }, [highlightCallId]);

    useEffect(() => {
      const last = items[items.length - 1];
      if (last?.kind === "msg" && last.role === "user") {
        followTailRef.current = true;
      }
      maybeStickBottom();
    }, [stickKey, items, maybeStickBottom]);

    function onScroll(e: UIEvent<HTMLDivElement>) {
      const el = e.currentTarget;
      const near = nearBottom(el);
      followTailRef.current = near;
      setAtBottom(near);
    }

    const scrollToBottom = useCallback((smooth = false) => {
      const el = scrollerRef.current;
      if (!el) return;
      followTailRef.current = true;
      el.scrollTo({ top: el.scrollHeight, behavior: smooth ? "smooth" : "auto" });
      setAtBottom(true);
    }, []);

    function wrapMotion(id: string, child: ReactNode, live = false) {
      // Keep one stable wrapper — toggling div/motion.div when `live` flips causes flicker.
      if (reducedMotion) {
        return (
          <div key={id} className="w-full">
            {child}
          </div>
        );
      }
      return (
        <motion.div key={id} layout={!live && !reducedMotion} {...itemMotion} className="w-full">
          {child}
        </motion.div>
      );
    }

    return (
      <div className={cn("relative flex min-h-0 flex-1 flex-col", className)}>
      <div
        ref={scrollerRef}
        className={cn(
          "messages flex min-h-0 flex-1 flex-col gap-2.5 overflow-y-auto overscroll-contain px-0.5 pb-3 pt-4",
          "[scrollbar-gutter:stable]",
        )}
        onScroll={onScroll}
      >
        {!items.length ? (
          <div className="empty-state m-auto max-w-md px-4 py-10 text-center text-muted-foreground animate-in fade-in duration-300">
            <div className="mb-3 flex justify-center">
              <NlmLogo className="size-14 shadow-md ring-1 ring-border/50" />
            </div>
            <div className="empty-brand mb-2 bg-gradient-to-r from-white via-[#8ec8f5] to-[#6fd4c0] bg-clip-text text-[22px] font-bold tracking-tight text-transparent">
              Nexus Lark Mind
            </div>
            <p className="m-0 text-sm">
              约一分钟就绪：绑定目录 → 选模型 → 描述任务。Agent 用 glob / grep / 读写 / shell 在项目里干活。
            </p>
            <ol className="empty-checklist mt-4 space-y-2 text-left text-[13px]">
              <li
                className={cn(
                  "rounded-lg border px-3 py-2",
                  hasWorkspace
                    ? "border-emerald-500/35 bg-emerald-500/10 text-foreground"
                    : "border-border/70 bg-muted/30",
                )}
              >
                <div className="font-medium text-foreground">
                  {hasWorkspace ? "✓ " : "1. "}绑定工作目录
                </div>
                {!hasWorkspace ? (
                  <div className="mt-0.5 text-[12px] text-muted-foreground">
                    选一个本地项目根目录，工具才能读写文件。
                  </div>
                ) : null}
              </li>
              <li
                className={cn(
                  "rounded-lg border px-3 py-2",
                  hasModel
                    ? "border-emerald-500/35 bg-emerald-500/10 text-foreground"
                    : "border-border/70 bg-muted/30",
                )}
              >
                <div className="font-medium text-foreground">
                  {hasModel ? "✓ " : "2. "}选择 Provider / 模型
                </div>
                <div className="mt-0.5 text-[12px] text-muted-foreground">
                  {hasModel
                    ? `${modelProvider}/${modelName}`
                    : "在下方输入框旁的模型菜单中选择（需已配置 API Key）。"}
                </div>
              </li>
              <li
                className={cn(
                  "rounded-lg border px-3 py-2",
                  hasWorkspace && hasModel
                    ? "border-border/70 bg-muted/20 text-foreground"
                    : "border-border/40 bg-transparent opacity-70",
                )}
              >
                <div className="font-medium">3. 描述任务并发送</div>
                <div className="mt-0.5 text-[12px] text-muted-foreground">
                  例如「梳理目录结构」或「修这个报错」。可用体验档控制图示精度。
                </div>
              </li>
            </ol>
            {showWorkspacePicker ? (
              <WorkspacePicker
                className="empty-ws mt-[18px]"
                compact
                onBound={(meta) => onPickWorkspace?.(meta)}
              />
            ) : null}
          </div>
        ) : null}

        {hiddenCount > 0 ? (
          <button
            type="button"
            className="mx-auto mb-1 rounded-md border border-border/60 bg-muted/40 px-3 py-1.5 text-xs text-muted-foreground hover:bg-muted/70"
            onClick={loadEarlier}
          >
            加载更早的消息（还有 {hiddenCount} 条）
          </button>
        ) : null}

        <AnimatePresence initial={false} mode="sync">
          {blocks.map((block) => {
            if (block.kind === "turn_process") {
              return wrapMotion(
                block.id,
                <TurnProcessFold
                  summary={block.summary}
                  reasoning={block.reasoning}
                  tools={block.tools}
                  subagents={block.subagents}
                  highlightCallId={highlightCallId}
                  onInspectTool={onInspectTool}
                  onStopTool={onStopTool}
                />,
              );
            }
            if (block.kind === "msg") {
              const live = !!(block.item.streaming || block.item.live);
              return wrapMotion(
                block.id,
                <MessageBubble
                  item={block.item as any}
                  modelProvider={modelProvider}
                  modelName={modelName}
                  experienceTier={experienceTier}
                  onAcceptPlan={() => onAcceptPlan?.(block.item)}
                />,
                live,
              );
            }
            if (block.kind === "ask") {
              return wrapMotion(
                block.id,
                <AskUserForm
                  item={block.item as any}
                  onSubmit={(ev) =>
                    onResolveAsk?.({
                      item: block.item,
                      action: "submit",
                      answers: ev.answers as Record<string, unknown> | undefined,
                    })
                  }
                  onDismiss={() => onResolveAsk?.({ item: block.item, action: "deny" })}
                />,
              );
            }
            if (block.kind === "plan_review") {
              return wrapMotion(
                block.id,
                <PlanReviewCard
                  item={block.item as any}
                  modelProvider={modelProvider}
                  modelName={modelName}
                  onResolve={(ev) =>
                    onResolvePlanReview?.({
                      item: block.item,
                      action: ev.action,
                      feedback: ev.feedback || "",
                    })
                  }
                />,
              );
            }
            if (block.kind === "todos") {
              return wrapMotion(block.id, <TodoListCard item={block.item as any} />);
            }
            if (block.kind === "subagent") {
              return wrapMotion(
                block.id,
                <SubagentCard
                  item={block.item as any}
                  onInspect={onInspectTool}
                  onStop={onStopTool}
                />,
                block.item.status === "running",
              );
            }
            if (block.kind === "file") {
              return wrapMotion(
                block.id,
                <ChatFileCard item={block.item as any} />,
              );
            }
            if (block.kind === "tools") {
              const live = block.tools.some((t) => t?.status === "running");
              if (block.tools.length === 1) {
                const t = block.tools[0];
                return wrapMotion(
                  block.id,
                  <ToolCard
                    item={t as any}
                    highlighted={
                      !!highlightCallId &&
                      ((t as any).callId === highlightCallId || (t as any).id === highlightCallId)
                    }
                    onInspect={onInspectTool}
                    onStop={onStopTool}
                  />,
                  live,
                );
              }
              return wrapMotion(
                block.id,
                <ToolCallGroup
                  tools={block.tools as any}
                  highlightCallId={highlightCallId}
                  onInspect={onInspectTool}
                  onStop={onStopTool}
                />,
                live,
              );
            }
            return null;
          })}
        </AnimatePresence>
      </div>

      {!atBottom && items.length > 0 ? (
        <button
          type="button"
          className="absolute bottom-3 left-1/2 z-10 -translate-x-1/2 rounded-full border border-border/70 bg-background/95 px-3 py-1.5 text-xs text-foreground shadow-md backdrop-blur hover:bg-muted"
          onClick={() => scrollToBottom(true)}
        >
          回到底部
        </button>
      ) : null}
      </div>
    );
  },
);

export default ChatMessages;
