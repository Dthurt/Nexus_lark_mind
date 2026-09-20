/** Incremental preview reducer — apply one Office stream event at a time. */

import {
  collectOfficeIds,
  parseOfficeOutline,
  type OfficeOutline,
  type OfficeSlide,
  type OfficeWordBlock,
} from "@/lib/officeOutline";

export type OfficePreviewState = {
  outline: OfficeOutline | null;
  enteringIds: string[];
  writing: boolean;
  op: string;
};

export type OfficePreviewEvent = {
  op?: string;
  outline?: OfficeOutline | string | null;
  body?: string;
  block?: OfficeWordBlock;
  slide?: OfficeSlide;
  last_ids?: string[];
  writing?: boolean;
};

export function emptyOfficePreview(): OfficePreviewState {
  return { outline: null, enteringIds: [], writing: false, op: "" };
}

export function applyOfficePreview(
  prev: OfficePreviewState,
  event: OfficePreviewEvent,
): OfficePreviewState {
  if (event.writing === true && !event.outline && !event.body && !event.block && !event.slide) {
    return { ...prev, writing: true };
  }

  const incoming =
    parseOfficeOutline(event.outline || event.body || null) ||
    (event.outline && typeof event.outline === "object" ? event.outline : null);

  if (incoming) {
    const prevIds = new Set(collectOfficeIds(prev.outline));
    const nextIds = collectOfficeIds(incoming);
    const hinted = (incoming.last_ids || event.last_ids || []).filter(Boolean);
    const entering =
      hinted.length > 0 ? hinted : nextIds.filter((id) => id && !prevIds.has(id));
    return {
      outline: incoming,
      enteringIds: entering,
      writing: event.writing === true ? true : false,
      op: event.op || incoming.last_op || prev.op,
    };
  }

  if (!prev.outline) {
    return { ...prev, writing: !!event.writing };
  }

  const next: OfficeOutline = {
    ...prev.outline,
    blocks: [...(prev.outline.blocks || [])],
    slides: [...(prev.outline.slides || [])],
  };
  const entering: string[] = [];
  if (event.block) {
    const id = event.block.id;
    const idx = next.blocks!.findIndex((b) => b.id === id);
    if (idx >= 0) next.blocks![idx] = event.block;
    else {
      next.blocks!.push(event.block);
      entering.push(id);
    }
  }
  if (event.slide) {
    const id = event.slide.id;
    const idx = next.slides!.findIndex((s) => s.id === id);
    if (idx >= 0) next.slides![idx] = event.slide;
    else {
      next.slides!.push(event.slide);
      entering.push(id);
    }
  }
  if (event.last_ids?.length) entering.push(...event.last_ids.filter((id) => !entering.includes(id)));
  next.last_ids = entering;
  next.last_op = event.op || next.last_op;
  return {
    outline: next,
    enteringIds: entering,
    writing: event.writing === true ? true : false,
    op: event.op || next.last_op || "",
  };
}
