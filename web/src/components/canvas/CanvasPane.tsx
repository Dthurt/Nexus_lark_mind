import { LayoutTemplate, X } from "lucide-react";
import { toast } from "sonner";

import { getCanvasView } from "@/components/canvas/canvasRegistry";
import { MarkdownCanvasView } from "@/components/canvas/MarkdownCanvasView";
import { Button } from "@/components/ui/button";
import { postSessionCanvas } from "@/api/endpoints";
import type { CanvasSessionApi } from "@/hooks/useCanvasSession";
import { cn } from "@/lib/utils";

export type CanvasPaneProps = {
  canvas: CanvasSessionApi;
  modelProvider?: string;
  modelName?: string;
  experienceTier?: string;
  sessionId?: string;
  cwd?: string;
  workspaceKind?: string;
  className?: string;
};

export function CanvasPane({
  canvas,
  modelProvider = "",
  modelName = "",
  experienceTier = "balanced",
  sessionId = "",
  cwd = "",
  workspaceKind = "local",
  className,
}: CanvasPaneProps) {
  const { docs, active, activeId, selectDoc, closeDoc, closePane, updateActiveBody } = canvas;
  const View = active ? getCanvasView(active.kind) || MarkdownCanvasView : null;

  const persistActive = async () => {
    if (!active || !sessionId) return;
    const name =
      (active.title || active.kind || "Canvas").replace(/[^\w\u4e00-\u9fff.-]+/g, "_") +
      (active.kind === "echarts" || active.kind === "table"
        ? ".json"
        : active.kind === "mermaid"
          ? ".mmd"
          : ".md");
    try {
      const data = await postSessionCanvas(sessionId, {
        name,
        content: active.body,
        kind: active.kind,
        title: active.title,
        cwd: cwd || undefined,
        workspace_kind: workspaceKind,
      });
      const path = data?.workspace?.path;
      toast.success(path ? `已写入 ${path}` : "已发布到会话");
    } catch (err: any) {
      toast.error(String(err?.message || err));
    }
  };

  return (
    <aside
      className={cn(
        "nlm-canvas-pane flex min-h-0 min-w-0 flex-col overflow-hidden border-l border-border bg-card/40",
        className,
      )}
      aria-label="Canvas"
    >
      <div className="flex shrink-0 items-center gap-1 border-b border-border/70 px-2 py-1.5">
        <LayoutTemplate className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
        <span className="text-[11px] font-medium text-foreground/90">Canvas</span>
        <span className="text-[10px] text-muted-foreground">· 旁侧产物</span>
        {active && sessionId ? (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="ml-auto h-6 px-2 text-[10px]"
            title={cwd ? "写入 .nlm/canvases/ 并附聊天卡片" : "发布到会话（绑定本地工作区后可落盘）"}
            onClick={() => void persistActive()}
          >
            保存
          </Button>
        ) : null}
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className={cn("size-6", !(active && sessionId) && "ml-auto")}
          title="关闭 Canvas"
          onClick={closePane}
        >
          <X className="size-3.5" />
        </Button>
      </div>

      {docs.length > 0 ? (
        <div className="flex shrink-0 gap-0.5 overflow-x-auto border-b border-border/50 px-1.5 py-1">
          {docs.map((d) => (
            <div
              key={d.id}
              className={cn(
                "group inline-flex max-w-[140px] items-center gap-0.5 rounded-md border px-1.5 py-0.5 text-[11px]",
                d.id === activeId
                  ? "border-primary/35 bg-primary/10 text-foreground"
                  : "border-transparent text-muted-foreground hover:bg-muted/40",
              )}
            >
              <button
                type="button"
                className="min-w-0 truncate"
                title={d.title}
                onClick={() => selectDoc(d.id)}
              >
                {d.title}
              </button>
              <button
                type="button"
                className="size-4 shrink-0 rounded opacity-50 hover:bg-foreground/10 hover:opacity-100"
                title="关闭此页"
                onClick={() => closeDoc(d.id)}
              >
                ×
              </button>
            </div>
          ))}
        </div>
      ) : null}

      <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
        {!active || !View ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-2 px-4 text-center">
            <p className="m-0 text-[13px] font-medium text-foreground/90">Canvas 为空</p>
            <p className="m-0 max-w-[280px] text-[11px] leading-relaxed text-muted-foreground">
              从消息工具栏打开，或让 Agent 调用 open_canvas。插件可通过 registerCanvasView 扩展视图。
            </p>
          </div>
        ) : (
          <View
            doc={active}
            onCommit={updateActiveBody}
            modelProvider={modelProvider}
            modelName={modelName}
            experienceTier={experienceTier}
          />
        )}
      </div>
    </aside>
  );
}

export default CanvasPane;
