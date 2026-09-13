import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { CanvasEditorShell, useSyncedDraft } from "@/components/canvas/CanvasEditorShell";
import { renderMermaidIn, sanitizeMermaidSource } from "@/lib/markdown";

export type MermaidCanvasEditorProps = {
  source: string;
  onCommit: (body: string) => void;
};

export function MermaidCanvasEditor({ source, onCommit }: MermaidCanvasEditorProps) {
  const [draft, setDraft] = useSyncedDraft(source);
  const [paint, setPaint] = useState(source);
  const [mode, setMode] = useState<"preview" | "source" | "split">("split");
  const [status, setStatus] = useState("");
  const [statusError, setStatusError] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setPaint(source);
  }, [source]);

  useEffect(() => {
    const root = ref.current;
    if (!root) return;
    const body = sanitizeMermaidSource(paint) || paint;
    root.innerHTML = `<div class="mermaid-block" data-mermaid-host="1"><pre class="mermaid">${escapeHtml(body)}</pre></div>`;
    void renderMermaidIn(root, {});
    return () => {
      root.innerHTML = "";
    };
  }, [paint, mode]);

  const apply = () => {
    const next = draft.trim();
    if (!next) {
      setStatus("源码为空");
      setStatusError(true);
      return;
    }
    setPaint(next);
    onCommit(next);
    setStatus("已写回 Canvas");
    setStatusError(false);
    window.setTimeout(() => setStatus(""), 1200);
  };

  const previewOnly = () => {
    setPaint(draft.trim() || draft);
    setStatus("已刷新预览");
    setStatusError(false);
    window.setTimeout(() => setStatus(""), 900);
  };

  const copyFence = async () => {
    try {
      await navigator.clipboard.writeText("```mermaid\n" + draft.trim() + "\n```");
      setStatus("已复制 fence");
      setStatusError(false);
    } catch (err: any) {
      setStatus(String(err?.message || err));
      setStatusError(true);
    }
  };

  return (
    <CanvasEditorShell
      kindLabel="Mermaid"
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
      <div ref={ref} className="nlm-canvas-mermaid min-h-[160px] p-2" />
    </CanvasEditorShell>
  );
}

function escapeHtml(s: string) {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
