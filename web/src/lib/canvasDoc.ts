/** Session Canvas docs — Cursor-like side artifacts (P1). */

import { parseOfficeOutline } from "@/lib/officeOutline";

export type CanvasDocKind =
  | "markdown"
  | "mermaid"
  | "drawio"
  | "echarts"
  | "delivery"
  | "table"
  | "office";

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

export type CanvasSessionState = {
  open: boolean;
  activeId: string | null;
  docs: CanvasDoc[];
  recent?: CanvasDoc[];
};

/** Stable fallback so every office write in a session can find the same pane. */
export const OFFICE_SESSION_SOURCE = "nlm.office.session";

export function newCanvasId(): string {
  return `cv_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`;
}

export function officeDocIdFromBody(body: string | undefined): string {
  if (!body) return "";
  return parseOfficeOutline(body)?.doc_id || "";
}

export function officeIdFromDoc(doc: CanvasDoc): string {
  const fromBody = officeDocIdFromBody(doc.body);
  if (fromBody) return fromBody;
  const src = String(doc.source || "").trim();
  return src.startsWith("off_") ? src : "";
}

export function needsOfficeHydration(doc: CanvasDoc): boolean {
  return doc.kind === "office" && !parseOfficeOutline(doc.body);
}

export function archiveCanvasDoc(recent: CanvasDoc[], doc: CanvasDoc, max = 8): CanvasDoc[] {
  return [doc, ...recent.filter((d) => d.id !== doc.id && d.source !== doc.source)].slice(0, max);
}

export function rememberRecentDocs(recent: CanvasDoc[], docs: CanvasDoc[], max = 8): CanvasDoc[] {
  const seen = new Set<string>();
  const out: CanvasDoc[] = [];
  for (const d of [...docs, ...recent]) {
    const key = `${d.kind}:${d.source || d.id}`;
    if (seen.has(key) || seen.has(d.id)) continue;
    seen.add(key);
    seen.add(d.id);
    out.push(d);
    if (out.length >= max) break;
  }
  return out;
}

export function normalizeCanvasDocs(raw: unknown): CanvasDoc[] {
  if (!Array.isArray(raw)) return [];
  return raw.filter((d): d is CanvasDoc => !!d && typeof d === "object" && typeof (d as CanvasDoc).id === "string");
}

export function canvasDocSource(input: OpenCanvasInput): string {
  const kind = input.kind || "markdown";
  if (kind === "office") {
    return (
      input.dedupeKey ||
      officeDocIdFromBody(input.body) ||
      input.source ||
      OFFICE_SESSION_SOURCE
    );
  }
  return input.source || input.dedupeKey || "";
}

export function findReusableCanvasDoc(
  docs: CanvasDoc[],
  input: OpenCanvasInput,
  opts?: { activeId?: string | null; paneOpen?: boolean },
): CanvasDoc | undefined {
  const kind = input.kind || "markdown";
  const dedupe = (input.dedupeKey || input.source || "").trim();
  const officeId = kind === "office" ? officeDocIdFromBody(input.body) : "";
  const keys = new Set([dedupe, officeId].filter(Boolean));

  if (kind === "office") {
    const officeDocs = docs.filter((d) => d.kind === "office");
    const keyed = officeDocs.find((d) => {
      const bodyId = officeDocIdFromBody(d.body);
      return keys.has(d.source || "") || keys.has(d.id) || (bodyId && keys.has(bodyId));
    });
    if (keyed) return keyed;
    if (officeDocs[0]) return officeDocs[0];
    if (opts?.paneOpen && docs.length) {
      return (opts.activeId && docs.find((d) => d.id === opts.activeId)) || docs[0];
    }
    return undefined;
  }

  if (!dedupe) return undefined;
  return docs.find((d) => (d.source === dedupe || d.id === dedupe) && d.kind === kind);
}

export function mergeCanvasDoc(existing: CanvasDoc, input: OpenCanvasInput): CanvasDoc {
  const kind = input.kind || existing.kind;
  return {
    ...existing,
    kind,
    body: input.body,
    title: input.title?.trim() || existing.title,
    source: kind === "office" ? canvasDocSource(input) : existing.source || canvasDocSource(input),
    updatedAt: new Date().toISOString(),
  };
}

export function applyCanvasOpen(
  docs: CanvasDoc[],
  input: OpenCanvasInput,
  opts?: { activeId?: string | null; paneOpen?: boolean },
): { docs: CanvasDoc[]; activeId: string; reused: boolean } {
  const hit = findReusableCanvasDoc(docs, input, opts);
  if (hit) {
    return {
      docs: docs.map((d) => (d.id === hit.id ? mergeCanvasDoc(d, input) : d)),
      activeId: hit.id,
      reused: true,
    };
  }
  const created = createCanvasDoc(input);
  return {
    docs: [created, ...docs].slice(0, 24),
    activeId: created.id,
    reused: false,
  };
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
              : kind === "office"
                ? "Office"
                : "Canvas");
  return {
    id: newCanvasId(),
    title,
    kind,
    body: input.body || "",
    updatedAt: new Date().toISOString(),
    source: canvasDocSource(input),
  };
}

const STORAGE_PREFIX = "nlm_canvas_";

export function loadCanvasSession(sessionId: string): CanvasSessionState {
  if (!sessionId) return { open: false, activeId: null, docs: [], recent: [] };
  try {
    const raw = localStorage.getItem(STORAGE_PREFIX + sessionId);
    if (!raw) return { open: false, activeId: null, docs: [], recent: [] };
    const parsed = JSON.parse(raw);
    const docs = normalizeCanvasDocs(parsed.docs);
    const recent = normalizeCanvasDocs(parsed.recent);
    return {
      open: !!parsed.open,
      activeId: parsed.activeId || docs[0]?.id || null,
      docs,
      recent: recent.length ? recent : docs.slice(0, 8),
    };
  } catch {
    return { open: false, activeId: null, docs: [], recent: [] };
  }
}

export function saveCanvasSession(sessionId: string, state: CanvasSessionState): void {
  if (!sessionId) return;
  try {
    const docs = state.docs.slice(0, 24);
    localStorage.setItem(
      STORAGE_PREFIX + sessionId,
      JSON.stringify({
        open: state.open,
        activeId: state.activeId,
        docs,
        recent: rememberRecentDocs(state.recent || [], docs).slice(0, 8),
      }),
    );
  } catch {
    /* ignore quota */
  }
}

/** Window event name for opening canvas from markdown chrome. */
export const NLM_CANVAS_OPEN_EVENT = "nlm-canvas-open";

export type CanvasOpenEventDetail = OpenCanvasInput;
