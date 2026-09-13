import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import type { CanvasViewProps } from "@/components/canvas/canvasRegistry";
import { CanvasEditorShell, useSyncedDraft } from "@/components/canvas/CanvasEditorShell";
import { MarkdownBody } from "@/components/chat/MarkdownBody";

export function MarkdownCanvasView({
  doc,
  onCommit,
  modelProvider = "",
  modelName = "",
  experienceTier = "balanced",
}: CanvasViewProps) {
  const [draft, setDraft] = useSyncedDraft(doc.body);
  const [paint, setPaint] = useState(doc.body);
  const [mode, setMode] = useState<"preview" | "source" | "split">("split");
  const [status, setStatus] = useState("");

  useEffect(() => {
    setPaint(doc.body);
  }, [doc.body]);

  const apply = () => {
    setPaint(draft);
    onCommit(draft);
    setStatus("已写回 Canvas");
    window.setTimeout(() => setStatus(""), 1200);
  };

  return (
    <CanvasEditorShell
      kindLabel={doc.kind === "delivery" ? "Delivery" : "Markdown"}
      draft={draft}
      onDraftChange={setDraft}
      onApply={apply}
      status={status}
      editorMode={mode}
      onEditorModeChange={setMode}
      extraActions={
        <Button
          type="button"
          size="sm"
          variant="ghost"
          className="h-6 px-2 text-[11px]"
          onClick={() => {
            setPaint(draft);
            setStatus("已刷新预览");
            window.setTimeout(() => setStatus(""), 900);
          }}
        >
          预览
        </Button>
      }
    >
      <div className="min-h-[160px] overflow-auto px-3 py-2">
        <MarkdownBody
          content={paint}
          streaming={false}
          modelProvider={modelProvider}
          modelName={modelName}
          experienceTier={experienceTier}
        />
      </div>
    </CanvasEditorShell>
  );
}
