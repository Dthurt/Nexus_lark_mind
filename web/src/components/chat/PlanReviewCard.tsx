import { useState } from "react";

import { MarkdownBody } from "@/components/chat/MarkdownBody";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

export type PlanReviewItem = {
  title?: string;
  plan?: string;
  status?: string;
};

export type PlanReviewCardProps = {
  item: PlanReviewItem;
  modelProvider?: string;
  modelName?: string;
  onResolve?: (ev: {
    action: "approve" | "keep_planning" | "deny";
    feedback?: string;
  }) => void;
  className?: string;
};

export function PlanReviewCard({
  item,
  modelProvider = "",
  modelName = "",
  onResolve,
  className,
}: PlanReviewCardProps) {
  const pending = item.status === "pending";
  const [feedback, setFeedback] = useState("");

  const stateLabel =
    item.status === "approved"
      ? "已批准"
      : item.status === "keep_planning"
        ? "继续规划"
        : item.status;

  return (
    <div
      className={cn(
        "my-2.5 max-w-[48rem] rounded-xl border border-teal/35 bg-teal/5 px-3.5 py-3",
        item.status === "approved" && "opacity-92",
        (item.status === "keep_planning" || item.status === "dismissed") && "opacity-85",
        className,
      )}
    >
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className="rounded-full border border-teal/40 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-teal">
          计划审阅
        </span>
        <span className="text-[13px] font-medium text-foreground">
          {item.title || "Approve this plan and leave plan mode?"}
        </span>
        {!pending ? <span className="ml-auto text-xs text-muted-foreground">{stateLabel}</span> : null}
      </div>

      <div className="mb-2.5 max-h-80 overflow-auto border-y border-border px-0.5 py-1.5">
        {item.plan ? (
          <MarkdownBody
            content={item.plan}
            streaming={false}
            plain={false}
            modelProvider={modelProvider}
            modelName={modelName}
          />
        ) : null}
      </div>

      {pending ? (
        <div>
          <Textarea
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            rows={2}
            placeholder="可选：留下修改意见（点「继续规划」时带回给模型）"
            className="mb-2 min-h-[52px] resize-y text-[13px]"
          />
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              size="sm"
              className="h-8 border border-teal/45 bg-teal/20 px-3 text-[13px] font-semibold text-foreground hover:bg-teal/30"
              onClick={() => onResolve?.({ action: "approve" })}
            >
              批准并执行
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-8 px-3 text-[13px]"
              onClick={() =>
                onResolve?.({ action: "keep_planning", feedback: feedback.trim() })
              }
            >
              继续规划
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-8 px-3 text-[13px]"
              onClick={() => onResolve?.({ action: "deny" })}
            >
              稍后自己说
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export default PlanReviewCard;
