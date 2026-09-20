/**
 * Register builtin Canvas views (CANVAS_VIEW slot). Import from main.tsx.
 */
import type { ComponentType } from "react";

import { registerCanvasView, type CanvasViewProps } from "@/components/canvas/canvasRegistry";
import { DrawioCanvasEditor } from "@/components/canvas/DrawioCanvasEditor";
import { EchartsCanvasEditor } from "@/components/canvas/EchartsCanvasEditor";
import { MarkdownCanvasView } from "@/components/canvas/MarkdownCanvasView";
import { MermaidCanvasEditor } from "@/components/canvas/MermaidCanvasEditor";
import { OfficeCanvasView } from "@/components/canvas/OfficeCanvasView";
import { TableCanvasView } from "@/components/canvas/TableCanvasView";

function wrapEditor(
  Editor: ComponentType<{ source: string; onCommit: (body: string) => void }>,
): ComponentType<CanvasViewProps> {
  return function CanvasEditorAdapter({ doc, onCommit }: CanvasViewProps) {
    return <Editor source={doc.body} onCommit={onCommit} />;
  };
}

registerCanvasView("mermaid", wrapEditor(MermaidCanvasEditor));
registerCanvasView("echarts", wrapEditor(EchartsCanvasEditor));
registerCanvasView("drawio", wrapEditor(DrawioCanvasEditor));
registerCanvasView("table", TableCanvasView);
registerCanvasView("markdown", MarkdownCanvasView);
registerCanvasView("delivery", MarkdownCanvasView);
registerCanvasView("office", OfficeCanvasView);

export {};
