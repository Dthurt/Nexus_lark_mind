import { useCallback, useEffect, useMemo, useState } from "react";

import {
  createCanvasDoc,
  loadCanvasSession,
  NLM_CANVAS_OPEN_EVENT,
  saveCanvasSession,
  type CanvasDoc,
  type CanvasOpenEventDetail,
  type OpenCanvasInput,
} from "@/lib/canvasDoc";

export function useCanvasSession(sessionId: string) {
  const [open, setOpen] = useState(false);
  const [docs, setDocs] = useState<CanvasDoc[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);

  useEffect(() => {
    const snap = loadCanvasSession(sessionId);
    setOpen(snap.open);
    setDocs(snap.docs);
    setActiveId(snap.activeId || snap.docs[0]?.id || null);
  }, [sessionId]);

  useEffect(() => {
    if (!sessionId) return;
    saveCanvasSession(sessionId, { open, activeId, docs });
  }, [sessionId, open, activeId, docs]);

  const active = useMemo(
    () => docs.find((d) => d.id === activeId) || docs[0] || null,
    [docs, activeId],
  );

  const openDoc = useCallback((input: OpenCanvasInput) => {
    const dedupe = input.dedupeKey || input.source || "";
    setDocs((prev) => {
      if (dedupe) {
        const hit = prev.find(
          (d) =>
            (d.source === dedupe || d.id === dedupe) &&
            d.kind === (input.kind || "markdown"),
        );
        if (hit) {
          const next = prev.map((d) =>
            d.id === hit.id
              ? {
                  ...d,
                  body: input.body,
                  title: input.title?.trim() || d.title,
                  updatedAt: new Date().toISOString(),
                }
              : d,
          );
          setActiveId(hit.id);
          setOpen(true);
          return next;
        }
      }
      const doc = createCanvasDoc(input);
      setActiveId(doc.id);
      setOpen(true);
      return [doc, ...prev].slice(0, 24);
    });
  }, []);

  const closePane = useCallback(() => setOpen(false), []);
  const togglePane = useCallback(() => setOpen((v) => !v), []);

  const closeDoc = useCallback((id: string) => {
    setDocs((prev) => {
      const next = prev.filter((d) => d.id !== id);
      setActiveId((cur) => {
        if (cur !== id) return cur;
        return next[0]?.id || null;
      });
      if (!next.length) setOpen(false);
      return next;
    });
  }, []);

  const selectDoc = useCallback((id: string) => {
    setActiveId(id);
    setOpen(true);
  }, []);

  const updateDoc = useCallback(
    (id: string, patch: Partial<Pick<CanvasDoc, "body" | "title" | "kind">>) => {
      setDocs((prev) =>
        prev.map((d) =>
          d.id === id
            ? {
                ...d,
                ...patch,
                updatedAt: new Date().toISOString(),
              }
            : d,
        ),
      );
    },
    [],
  );

  const updateActiveBody = useCallback(
    (body: string) => {
      if (!activeId) return;
      updateDoc(activeId, { body });
    },
    [activeId, updateDoc],
  );

  useEffect(() => {
    const onOpen = (ev: Event) => {
      const detail = (ev as CustomEvent<CanvasOpenEventDetail>).detail;
      if (!detail?.body) return;
      openDoc(detail);
    };
    window.addEventListener(NLM_CANVAS_OPEN_EVENT, onOpen as EventListener);
    return () => window.removeEventListener(NLM_CANVAS_OPEN_EVENT, onOpen as EventListener);
  }, [openDoc]);

  return {
    open,
    setOpen,
    docs,
    active,
    activeId,
    openDoc,
    closePane,
    togglePane,
    closeDoc,
    selectDoc,
    updateDoc,
    updateActiveBody,
  };
}

export type CanvasSessionApi = ReturnType<typeof useCanvasSession>;
