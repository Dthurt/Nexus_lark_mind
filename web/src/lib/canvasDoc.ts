/** Session Canvas docs — Cursor-like side artifacts (P1). */

export type CanvasDocKind =
  | "markdown"
  | "mermaid"
  | "drawio"
  | "echarts"
  | "delivery"
  | "table";

export type CanvasDoc = {
  id: string;
  title: string;
  kind: CanvasDocKind;
  body: string;
  updatedAt: string;
  source?: string;
};

export type OpenCanvasInput = {
  title?: string;
  kind?: CanvasDocKind;
  body: string;
  source?: string;
  /** Reuse existing doc with same source+kind when possible */
  dedupeKey?: string;
};

export function newCanvasId(): string {
  return `cv_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`;
}

export function createCanvasDoc(input: OpenCanvasInput): CanvasDoc {
  const kind = input.kind || "markdown";
  const title =
    (input.title || "").trim() ||
    (kind === "mermaid"
      ? "Mermaid"
      : kind === "delivery"
        ? "Delivery"
        : kind === "drawio"
          ? "Draw.io"
          : kind === "echarts"
            ? "ECharts"
            : kind === "table"
              ? "Table"
              : "Canvas");
  return {
    id: newCanvasId(),
    title,
    kind,
    body: input.body || "",
    updatedAt: new Date().toISOString(),
    source: input.source || input.dedupeKey || "",
  };
}

const STORAGE_PREFIX = "nlm_canvas_";

export function loadCanvasSession(sessionId: string): {
  open: boolean;
  activeId: string | null;
  docs: CanvasDoc[];
} {
  if (!sessionId) return { open: false, activeId: null, docs: [] };
  try {
    const raw = localStorage.getItem(STORAGE_PREFIX + sessionId);
    if (!raw) return { open: false, activeId: null, docs: [] };
    const parsed = JSON.parse(raw);
    return {
      open: !!parsed.open,
      activeId: parsed.activeId || null,
      docs: Array.isArray(parsed.docs) ? parsed.docs : [],
    };
  } catch {
    return { open: false, activeId: null, docs: [] };
  }
}

export function saveCanvasSession(
  sessionId: string,
  state: { open: boolean; activeId: string | null; docs: CanvasDoc[] },
): void {
  if (!sessionId) return;
  try {
    localStorage.setItem(
      STORAGE_PREFIX + sessionId,
      JSON.stringify({
        open: state.open,
        activeId: state.activeId,
        docs: state.docs.slice(0, 24),
      }),
    );
  } catch {
    /* ignore quota */
  }
}

/** Window event name for opening canvas from markdown chrome. */
export const NLM_CANVAS_OPEN_EVENT = "nlm-canvas-open";

export type CanvasOpenEventDetail = OpenCanvasInput;
