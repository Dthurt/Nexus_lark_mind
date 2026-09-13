import { listRegisteredCanvasViews } from "@/components/canvas/canvasRegistry";
import { listRegisteredToolViews } from "@/components/tools/toolRegistry";
import { listAllSlots, listSlotKeys, SlotNames } from "@/runtime/pluginSlots";

/** Shows Cordis-lite slot contributions currently registered in the SPA. */
export function ExtensionsPanel() {
  const toolViews = listRegisteredToolViews();
  const canvasViews = listRegisteredCanvasViews();
  const all = listAllSlots();

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto overscroll-contain p-2.5">
      <p className="m-0 text-[10.5px] leading-relaxed text-muted-foreground">
        扩展槽（Cordis-lite）：前端用 <span className="font-mono">registerSlot / registerToolView / registerCanvasView</span>{" "}
        注册，不是完整 Cordis fiber 图。
      </p>

      <section className="space-y-1">
        <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
          {SlotNames.TOOL_CALL_VIEW}
        </div>
        <p className="m-0 text-[10.5px] text-muted-foreground">
          已注册工具卡片视图 · {toolViews.length}
        </p>
        <div className="flex flex-wrap gap-1">
          {toolViews.map((k) => (
            <span
              key={k}
              className="rounded border border-border/60 bg-background/40 px-1.5 py-0.5 font-mono text-[10px]"
            >
              {k}
            </span>
          ))}
          {!toolViews.length ? (
            <span className="text-[10.5px] text-muted-foreground">无</span>
          ) : null}
        </div>
      </section>

      <section className="space-y-1">
        <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
          {SlotNames.CANVAS_VIEW}
        </div>
        <p className="m-0 text-[10.5px] text-muted-foreground">
          已注册 Canvas 文档视图 · {canvasViews.length}
        </p>
        <div className="flex flex-wrap gap-1">
          {canvasViews.map((k) => (
            <span
              key={k}
              className="rounded border border-border/60 bg-background/40 px-1.5 py-0.5 font-mono text-[10px]"
            >
              {k}
            </span>
          ))}
          {!canvasViews.length ? (
            <span className="text-[10.5px] text-muted-foreground">无</span>
          ) : null}
        </div>
      </section>

      <section className="space-y-1">
        <div className="text-[10px] uppercase tracking-wide text-muted-foreground">全部槽位</div>
        {all.map((row) => (
          <div key={row.slot} className="rounded-md border border-border/50 px-2 py-1.5">
            <div className="font-mono text-[11px] text-foreground/90">{row.slot}</div>
            <div className="mt-0.5 font-mono text-[10px] text-muted-foreground">
              {row.keys.join(", ") || "(empty)"}
            </div>
          </div>
        ))}
        {!all.length ? (
          <p className="m-0 text-[10.5px] text-muted-foreground">暂无注册</p>
        ) : null}
      </section>

      <p className="m-0 text-[10px] text-muted-foreground">
        预留槽：{SlotNames.COMPOSER_ACTION}、{SlotNames.DOCK_PANEL}
      </p>
      <p className="m-0 font-mono text-[10px] text-muted-foreground">
        composer keys: {listSlotKeys(SlotNames.COMPOSER_ACTION).join(", ") || "—"}
      </p>
    </div>
  );
}

export default ExtensionsPanel;
