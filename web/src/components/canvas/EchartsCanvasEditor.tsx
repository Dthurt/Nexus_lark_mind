import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { CanvasEditorShell, useSyncedDraft } from "@/components/canvas/CanvasEditorShell";
import { parseEchartsOption } from "@/lib/markdown";
import { diagramPanelBg, isLightDiagramTheme } from "@/lib/markdown/diagramTheme";

export type EchartsCanvasEditorProps = {
  source: string;
  onCommit: (body: string) => void;
};

export function EchartsCanvasEditor({ source, onCommit }: EchartsCanvasEditorProps) {
  const [draft, setDraft] = useSyncedDraft(source);
  const [paint, setPaint] = useState(source);
  const [mode, setMode] = useState<"preview" | "source" | "split">("split");
  const [status, setStatus] = useState("");
  const [statusError, setStatusError] = useState(false);
  const hostRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<any>(null);

  useEffect(() => {
    setPaint(source);
  }, [source]);

  useEffect(() => {
    let disposed = false;
    const host = hostRef.current;
    if (!host) return;

    void (async () => {
      try {
        const option = parseEchartsOption(paint);
        const mod = await import("echarts");
        const echarts = (mod as any).default?.init ? (mod as any).default : mod;
        if (disposed || !hostRef.current) return;
        if (chartRef.current) {
          try {
            chartRef.current.dispose();
          } catch {
            /* ignore */
          }
          chartRef.current = null;
        }
        host.innerHTML = "";
        const el = document.createElement("div");
        el.style.width = "100%";
        el.style.height = "100%";
        el.style.minHeight = "220px";
        host.appendChild(el);
        const chart = echarts.init(el, isLightDiagramTheme() ? undefined : "dark");
        chart.setOption(
          {
            backgroundColor: diagramPanelBg(),
            ...option,
          },
          true,
        );
        chartRef.current = chart;
        setStatusError(false);
      } catch (err: any) {
        if (disposed) return;
        setStatus(String(err?.message || err || "ECharts 解析失败"));
        setStatusError(true);
        if (host) host.innerHTML = "";
      }
    })();

    return () => {
      disposed = true;
      if (chartRef.current) {
        try {
          chartRef.current.dispose();
        } catch {
          /* ignore */
        }
        chartRef.current = null;
      }
    };
  }, [paint, mode]);

  useEffect(() => {
    const onResize = () => {
      try {
        chartRef.current?.resize?.();
      } catch {
        /* ignore */
      }
    };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  const apply = () => {
    try {
      const opt = parseEchartsOption(draft);
      const pretty = JSON.stringify(opt, null, 2);
      setDraft(pretty);
      setPaint(pretty);
      onCommit(pretty);
      setStatus("已写回 Canvas");
      setStatusError(false);
      window.setTimeout(() => setStatus(""), 1200);
    } catch (err: any) {
      setStatus(String(err?.message || err));
      setStatusError(true);
    }
  };

  const previewOnly = () => {
    try {
      parseEchartsOption(draft);
      setPaint(draft);
      setStatus("已刷新预览");
      setStatusError(false);
      window.setTimeout(() => setStatus(""), 900);
    } catch (err: any) {
      setStatus(String(err?.message || err));
      setStatusError(true);
    }
  };

  const copyFence = async () => {
    try {
      await navigator.clipboard.writeText("```echarts\n" + draft.trim() + "\n```");
      setStatus("已复制 fence");
      setStatusError(false);
    } catch (err: any) {
      setStatus(String(err?.message || err));
      setStatusError(true);
    }
  };

  return (
    <CanvasEditorShell
      kindLabel="ECharts"
      draft={draft}
      onDraftChange={setDraft}
      onApply={apply}
      status={status}
      statusError={statusError}
      editorMode={mode}
      onEditorModeChange={setMode}
      extraActions={
        <>
          <Button type="button" size="sm" variant="ghost" className="h-6 px-2 text-[11px]" onClick={previewOnly}>
            预览
          </Button>
          <Button type="button" size="sm" variant="ghost" className="h-6 px-2 text-[11px]" onClick={() => void copyFence()}>
            复制
          </Button>
        </>
      }
    >
      <div ref={hostRef} className="nlm-canvas-echarts min-h-[220px] p-2" />
    </CanvasEditorShell>
  );
}
