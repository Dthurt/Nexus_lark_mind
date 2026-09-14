import { memo, useEffect, useMemo, useState } from "react";
import { Check, Copy } from "lucide-react";
import { toast } from "sonner";

import { ActivityHint } from "@/components/chat/ActivityHint";
import { MarkdownBody } from "@/components/chat/MarkdownBody";
import { ThinkingFold } from "@/components/chat/ThinkingFold";
import { Button } from "@/components/ui/button";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  cacheHitRate,
  estimateCostCny,
  formatCacheHit,
  formatCny,
  formatDurationMs,
  formatTokenCount,
  formatUsageLine,
  resolveModelRate,
} from "@/lib/pricing";
import { cn } from "@/lib/utils";

export type MessageBubbleItem = {
  role: string;
  content?: string;
  reasoning?: string;
  rich?: boolean;
  streaming?: boolean;
  live?: boolean;
  usage?: any;
  modelName?: string;
  modelProvider?: string;
  hideReasoning?: boolean;
  activity?: {
    phase?: string;
    label?: string;
    detail?: string;
    startedAt?: number;
  } | null;
  planReady?: boolean;
};

export type MessageBubbleProps = {
  item: MessageBubbleItem;
  modelProvider?: string;
  modelName?: string;
  experienceTier?: "fast" | "balanced" | "high" | string;
  onAcceptPlan?: (item: MessageBubbleItem) => void;
  className?: string;
};

export const MessageBubble = memo(function MessageBubble({
  item,
  modelProvider = "",
  modelName = "",
  experienceTier = "balanced",
  onAcceptPlan,
  className,
}: MessageBubbleProps) {
  const [openUsage, setOpenUsage] = useState(false);
  const [content, setContent] = useState(item.content || "");
  const [copied, setCopied] = useState(false);
  const [userExpanded, setUserExpanded] = useState(false);

  useEffect(() => {
    setContent(item.content || "");
  }, [item.content]);

  const resolvedModel = item.modelName || modelName || "";
  const resolvedProvider = item.modelProvider || modelProvider || "";
  const footerModel = item.modelName || "";
  const footerProvider = item.modelProvider || modelProvider || "";

  const showCaret = useMemo(() => {
    if (!item.streaming) return false;
    const phase = item.activity?.phase;
    // Keep caret while model/stream so text paints live next to the spinner.
    return !phase || phase === "stream" || phase === "model";
  }, [item.streaming, item.activity?.phase]);

  const usageSummary = useMemo(() => {
    if (!item.usage) return "";
    return formatUsageLine(item.usage, {
      modelName: footerModel || resolvedModel,
      providerId: footerProvider,
    });
  }, [item.usage, footerModel, footerProvider, resolvedModel]);

  const usageDetail = useMemo(() => {
    const u = item.usage;
    if (!u) return null;
    const cost = estimateCostCny(u, {
      modelName: footerModel || resolvedModel,
      providerId: footerProvider,
    });
    const cache = formatCacheHit(u);
    const rate = resolveModelRate(footerModel || resolvedModel, footerProvider);
    return {
      model: footerModel || "—",
      prompt: formatTokenCount(Number(u.prompt_tokens || 0)),
      completion: formatTokenCount(Number(u.completion_tokens || 0)),
      total: formatTokenCount(
        Number(u.total_tokens || (u.prompt_tokens || 0) + (u.completion_tokens || 0)),
      ),
      duration: formatDurationMs(u.duration_ms) || "—",
      cacheText:
        cache.cached > 0
          ? `${formatTokenCount(cache.cached)} · ${cacheHitRate(u).toFixed(1)}%`
          : "0",
      costText: formatCny(cost.yuan),
      rateText: `输入 ¥${rate.input}/M · 输出 ¥${rate.output}/M · 缓存 ¥${rate.cache}/M`,
      estimated: !!u.estimated,
    };
  }, [item.usage, footerModel, footerProvider, resolvedModel]);

  function onMermaidFixed({ from, to }: { from: string; to: string }) {
    if (!from || !to || from === to) return;
    if (!content.includes(from)) return;
    const next = content.replace(from, to);
    item.content = next;
    setContent(next);
  }

  async function copyFullText() {
    const text = (content || "").trim();
    if (!text) {
      toast.error("没有可复制的内容");
      return;
    }
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      toast.success("已复制全文");
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      toast.error("复制失败");
    }
  }

  const isUser = item.role === "user";
  const showUsageFooter =
    !isUser && !item.streaming && !item.live && !!item.usage;
  const showCopyAction =
    !isUser && !item.streaming && !item.live && !!(content || "").trim();

  return (
    <div
      className={cn(
        "msg max-w-full min-w-0 animate-in fade-in duration-150 rounded-xl border px-3.5 py-2.5",
        isUser
          ? "ml-auto w-fit max-w-[min(92%,720px)] self-end rounded-br-sm border-primary/25 bg-primary/10"
          : "w-full self-start rounded-bl-sm border-transparent bg-transparent px-1 py-1.5 sm:px-2",
        (item.live || item.streaming) && "live",
        className,
      )}
    >
      {!isUser &&
      !item.hideReasoning &&
      (item.reasoning || (item.streaming && !(content || "").trim())) ? (
        <ThinkingFold
          text={item.reasoning || ""}
          streaming={!!item.streaming && !(content || "").trim()}
        />
      ) : null}

      {content ? (
        <div className="min-w-0">
          <MarkdownBody
            className={cn(
              "body",
              isUser &&
                !userExpanded &&
                "max-h-[10.5em] overflow-y-auto overscroll-contain [scrollbar-width:none] [&::-webkit-scrollbar]:hidden",
            )}
            content={content}
            streaming={!!item.streaming && showCaret}
            plain={!item.rich}
            modelProvider={resolvedProvider}
            modelName={resolvedModel}
            experienceTier={experienceTier}
            onMermaidFixed={onMermaidFixed}
          />
          {isUser && (content || "").length > 280 ? (
            <button
              type="button"
              className="mt-1 text-[11px] text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
              onClick={() => setUserExpanded((v) => !v)}
            >
              {userExpanded ? "收起" : "展开全部"}
            </button>
          ) : null}
        </div>
      ) : null}

      {item.activity && (item.streaming || item.live) ? (
        <ActivityHint
          embedded
          active
          phase={item.activity.phase}
          label={item.activity.label}
          detail={item.activity.detail}
          startedAt={item.activity.startedAt}
        />
      ) : null}

      {item.planReady && item.role === "assistant" && !item.streaming && !item.live ? (
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="mt-2 h-7 border-primary/45 bg-primary/10 px-3 text-xs text-primary hover:bg-primary/15"
          onClick={() => onAcceptPlan?.(item)}
        >
          接受计划并执行
        </Button>
      ) : null}

      {showUsageFooter || showCopyAction ? (
        <div className="mt-1.5 flex items-end gap-2">
          {showUsageFooter && usageDetail ? (
            <div className="min-w-0 flex-1">
              <Popover open={openUsage} onOpenChange={setOpenUsage}>
                <PopoverTrigger asChild>
                  <button
                    type="button"
                    className="token-badge max-w-full cursor-pointer border-0 bg-transparent p-0 text-left font-mono text-[11px] leading-snug text-muted-foreground hover:text-foreground"
                    title="点击查看明细"
                  >
                    {usageSummary}
                  </button>
                </PopoverTrigger>
                <PopoverContent
                  align="start"
                  side="top"
                  className="w-[300px] p-2.5 text-xs"
                  role="dialog"
                  aria-label="用量明细"
                >
                  {(
                    [
                      ["模型", usageDetail.model],
                      ["输入", usageDetail.prompt],
                      ["输出", usageDetail.completion],
                      ["合计", usageDetail.total],
                      ["耗时", usageDetail.duration],
                      ["缓存命中", usageDetail.cacheText],
                      ["估算费用", usageDetail.costText],
                    ] as const
                  ).map(([label, val]) => (
                    <div key={label} className="flex justify-between gap-3 py-0.5 text-[11px]">
                      <span className="text-muted-foreground">{label}</span>
                      <strong
                        className="max-w-[180px] truncate font-mono font-medium"
                        title={String(val)}
                      >
                        {val}
                      </strong>
                    </div>
                  ))}
                  <p className="mt-1 text-[10px] leading-snug text-muted-foreground">
                    {usageDetail.rateText}
                  </p>
                  {usageDetail.estimated ? (
                    <p className="mt-0.5 text-[10px] leading-snug text-muted-foreground">
                      含估算 token（接口未返回 usage）
                    </p>
                  ) : null}
                </PopoverContent>
              </Popover>
            </div>
          ) : (
            <div className="min-w-0 flex-1" />
          )}

          {showCopyAction ? (
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="size-7 shrink-0 text-muted-foreground hover:text-foreground"
              title="复制全文"
              aria-label="复制全文"
              onClick={() => void copyFullText()}
            >
              {copied ? (
                <Check className="size-3.5 text-emerald-600 dark:text-emerald-400" />
              ) : (
                <Copy className="size-3.5" />
              )}
            </Button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
});

export default MessageBubble;
