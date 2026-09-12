import { useEffect } from "react";

import { Button } from "@/components/ui/button";
import { MarkdownBody } from "@/components/chat/MarkdownBody";
import type { DeliveryArtifactApi } from "@/hooks/useDeliveryArtifact";
import { cn } from "@/lib/utils";

export type DeliveryPanelProps = {
  delivery: DeliveryArtifactApi;
  sessionId?: string;
  cwd?: string;
  workspaceKind?: string;
  className?: string;
};

export function DeliveryPanel({
  delivery,
  sessionId = "",
  cwd = "",
  workspaceKind = "local",
  className,
}: DeliveryPanelProps) {
  const art = delivery.current;

  useEffect(() => {
    delivery.setWorkspace(cwd, workspaceKind);
  }, [cwd, workspaceKind, delivery]);

  useEffect(() => {
    if (!art?.sessionId) return;
    const t = window.setInterval(() => {
      void delivery.syncMutations(art.sessionId);
    }, 8000);
    return () => window.clearInterval(t);
  }, [art?.sessionId, art?.id, delivery]);

  return (
    <div className={cn("flex min-h-0 flex-1 flex-col gap-2 overflow-auto p-2 text-[12px]", className)}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Delivery</div>
          <div className="truncate font-medium text-foreground" title={art?.title}>
            {art?.title || "尚无交付文档"}
          </div>
          <p className="m-0 mt-0.5 text-[11px] text-muted-foreground">
            Plan → 图示 → 改仓审计。批准后写入会话与{" "}
            <code className="text-[10px]">.nlm/deliveries/</code>
          </p>
        </div>
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="h-7 shrink-0 px-2"
          disabled={!art}
          onClick={() => void delivery.syncMutations(sessionId || art?.sessionId)}
        >
          同步变更
        </Button>
      </div>

      {!art ? (
        <p className="m-0 rounded-md border border-border/60 bg-muted/30 px-2 py-2 text-muted-foreground">
          在 <strong>计划</strong> 模式下让 Agent 产出带 Mermaid 的计划，点「批准并执行」后这里会出现 Delivery
          文档，并随 write/edit 工具填充「Code changes」。
        </p>
      ) : (
        <>
          <div className="text-[10px] text-muted-foreground">
            {art.fileName}
            {art.workspacePath ? ` · ${art.workspacePath}` : ""}
            {art.mutationLines.length ? ` · ${art.mutationLines.length} mutations` : ""}
          </div>
          <div className="min-h-0 flex-1 overflow-auto rounded-md border border-border/50 bg-background/40 px-2 py-1.5">
            <MarkdownBody content={art.markdown} streaming={false} plain={false} />
          </div>
        </>
      )}

      {delivery.history.length > 1 ? (
        <section>
          <div className="mb-1 text-[10px] uppercase tracking-wider text-muted-foreground">本会话历史</div>
          <ul className="m-0 list-none space-y-1 p-0">
            {delivery.history.slice(0, 6).map((h) => (
              <li key={h.id}>
                <button
                  type="button"
                  className={cn(
                    "w-full truncate rounded-md border px-2 py-1 text-left hover:bg-muted/50",
                    art?.id === h.id ? "border-teal/40 bg-teal/10" : "border-border/50",
                  )}
                  onClick={() => delivery.setCurrent(h)}
                >
                  {h.title}
                </button>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
