import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  type UIEvent,
} from "react";

import { AskUserForm } from "@/components/chat/AskUserForm";
import { MessageBubble } from "@/components/chat/MessageBubble";
import { PlanReviewCard } from "@/components/chat/PlanReviewCard";
import { SubagentCard } from "@/components/chat/SubagentCard";
import { TodoListCard } from "@/components/chat/TodoListCard";
import { ToolApprovalCard } from "@/components/chat/ToolApprovalCard";
import { ToolCallGroup } from "@/components/chat/ToolCallGroup";
import { ToolCard } from "@/components/chat/ToolCard";
import "@/components/tools/registerBuiltinTools";
import { WorkspacePicker } from "@/components/workspace/WorkspacePicker";
import type { TimelineItem } from "@/hooks/useChatTimeline";
import type { Workspace } from "@/types/api";
import { cn } from "@/lib/utils";

export type ChatMessagesProps = {
  items?: TimelineItem[];
  showWorkspacePicker?: boolean;
  modelProvider?: string;
  modelName?: string;
  onInspectTool?: (activityId: string) => void;
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
  className?: string;
};

export type ChatMessagesHandle = {
  el: HTMLDivElement | null;
  scrollBottom: () => void;
};

type Block =
  | { kind: "msg" | "approval" | "ask" | "todos" | "plan_review" | "subagent"; id: string; item: TimelineItem }
  | { kind: "tools"; id: string; tools: TimelineItem[] };

function nearBottom(el: HTMLElement, threshold = 80) {
  return el.scrollHeight - el.scrollTop - el.clientHeight < threshold;
}

function buildBlocks(items: TimelineItem[]): Block[] {
  const out: Block[] = [];
  for (const item of items || []) {
    if (
      item.kind === "approval" ||
      item.kind === "ask" ||
      item.kind === "todos" ||
      item.kind === "plan_review"
    ) {
      out.push({ kind: item.kind, id: item.id, item });
      continue;
    }
    if (item.kind === "tool") {
      const last = out[out.length - 1];
      if (last?.kind === "tools") {
        last.tools.push(item);
      } else {
        out.push({ kind: "tools", id: `tg-${item.id}`, tools: [item] });
      }
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
    out.push({ kind: "msg", id: item.id, item });
  }
  return out;
}

export const ChatMessages = forwardRef<ChatMessagesHandle, ChatMessagesProps>(
  function ChatMessages(
    {
      items = [],
      showWorkspacePicker = false,
      modelProvider = "",
      modelName = "",
      onInspectTool,
      onPickWorkspace,
      onResolveApproval,
      onResolveAsk,
      onResolvePlanReview,
      onAcceptPlan,
      className,
    },
    ref,
  ) {
    const scrollerRef = useRef<HTMLDivElement>(null);
    const followTailRef = useRef(true);

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

    const blocks = useMemo(() => buildBlocks(items), [items]);

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
      if (last.kind === "msg") return `${items.length}|${last.content || ""}`;
      if (last.kind === "subagent")
        return `${items.length}|${last.streamText || ""}|${last.status || ""}`;
      if (last.kind === "tool") return `${items.length}|${last.status || ""}|${last.open ? 1 : 0}`;
      return `${items.length}|${last.id || ""}`;
    }, [items]);

    useEffect(() => {
      const last = items[items.length - 1];
      if (last?.kind === "msg" && last.role === "user") {
        followTailRef.current = true;
      }
      maybeStickBottom();
    }, [stickKey, items, maybeStickBottom]);

    function onScroll(e: UIEvent<HTMLDivElement>) {
      followTailRef.current = nearBottom(e.currentTarget);
    }

    return (
      <div
        ref={scrollerRef}
        className={cn(
          "messages flex min-h-0 flex-1 flex-col gap-2.5 overflow-y-auto overscroll-contain px-0.5 pb-3 pt-4",
          className,
        )}
        onScroll={onScroll}
      >
        {!items.length ? (
          <div className="empty-state m-auto px-4 py-10 text-center text-muted-foreground">
            <div className="empty-brand mb-2 bg-gradient-to-r from-white via-[#8ec8f5] to-[#6fd4c0] bg-clip-text text-[22px] font-bold tracking-tight text-transparent">
              Nexus Lark Mind
            </div>
            <p className="m-0 text-sm">
              先绑定工作目录，再让 Coding Agent 用 glob / grep / 读写 / shell 在项目里干活。
              Agent 会按任务自行决定是否委派 subagent；飞书、插件坞与 Trajectory 仍是工作台能力。
            </p>
            {showWorkspacePicker ? (
              <WorkspacePicker
                className="empty-ws mt-[18px]"
                compact
                onBound={(meta) => onPickWorkspace?.(meta)}
              />
            ) : null}
          </div>
        ) : null}

        {blocks.map((block) => {
          if (block.kind === "msg") {
            return (
              <MessageBubble
                key={block.id}
                item={block.item as any}
                modelProvider={modelProvider}
                modelName={modelName}
                onAcceptPlan={() => onAcceptPlan?.(block.item)}
              />
            );
          }
          if (block.kind === "approval") {
            return (
              <ToolApprovalCard
                key={block.id}
                item={block.item as any}
                onResolve={(ev) =>
                  onResolveApproval?.({ item: block.item, action: ev.action })
                }
              />
            );
          }
          if (block.kind === "ask") {
            return (
              <AskUserForm
                key={block.id}
                item={block.item as any}
                onSubmit={(ev) =>
                  onResolveAsk?.({
                    item: block.item,
                    action: "submit",
                    answers: ev.answers as Record<string, unknown> | undefined,
                  })
                }
                onDismiss={() => onResolveAsk?.({ item: block.item, action: "deny" })}
              />
            );
          }
          if (block.kind === "plan_review") {
            return (
              <PlanReviewCard
                key={block.id}
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
              />
            );
          }
          if (block.kind === "todos") {
            return <TodoListCard key={block.id} item={block.item as any} />;
          }
          if (block.kind === "subagent") {
            return (
              <SubagentCard
                key={block.id}
                item={block.item as any}
                onInspect={onInspectTool}
              />
            );
          }
          if (block.kind === "tools") {
            if (block.tools.length > 1) {
              return (
                <ToolCallGroup
                  key={block.id}
                  tools={block.tools as any}
                  onInspect={onInspectTool}
                />
              );
            }
            return (
              <ToolCard
                key={block.id}
                item={block.tools[0] as any}
                onInspect={onInspectTool}
              />
            );
          }
          return null;
        })}
      </div>
    );
  },
);

export default ChatMessages;
