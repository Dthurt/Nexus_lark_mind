import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { getCanvasState, getOfficeOutline, listOfficeRecent, putCanvasState } from "@/api/endpoints";
import {
  applyCanvasOpen,
  archiveCanvasDoc,
  loadCanvasSession,
  needsOfficeHydration,
  NLM_CANVAS_OPEN_EVENT,
  normalizeCanvasDocs,
  officeIdFromDoc,
  rememberRecentDocs,
  saveCanvasSession,
  type CanvasDoc,
  type CanvasOpenEventDetail,
  type OpenCanvasInput,
} from "@/lib/canvasDoc";

export type UseCanvasSessionOpts = {
  cwd?: string;
  workspaceKind?: string;
};

export function useCanvasSession(sessionId: string, opts: UseCanvasSessionOpts = {}) {
  const cwd = opts.cwd || "";
  const workspaceKind = opts.workspaceKind || "local";
  const [open, setOpen] = useState(false);
  const [docs, setDocs] = useState<CanvasDoc[]>([]);
  const [recent, setRecent] = useState<CanvasDoc[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const openRef = useRef(open);
  const activeIdRef = useRef(activeId);
  const docsRef = useRef(docs);
  const recentRef = useRef(recent);
  const skipSaveRef = useRef(true);
  const persistTimer = useRef<number | null>(null);
  openRef.current = open;
  activeIdRef.current = activeId;
  docsRef.current = docs;
  recentRef.current = recent;

  useEffect(() => {
    skipSaveRef.current = true;
    const snap = loadCanvasSession(sessionId);
    setOpen(snap.open);
    setDocs(snap.docs);
    setRecent(snap.recent || []);
    setActiveId(snap.activeId || snap.docs[0]?.id || null);
  }, [sessionId]);

  useEffect(() => {
    if (!sessionId) return;
    if (skipSaveRef.current) {
      skipSaveRef.current = false;
      return;
    }
    const nextRecent = rememberRecentDocs(recent, docs);
    saveCanvasSession(sessionId, { open, activeId, docs, recent: nextRecent });
    if (persistTimer.current) window.clearTimeout(persistTimer.current);
    if (!cwd || workspaceKind === "ssh") return;
    persistTimer.current = window.setTimeout(() => {
      void putCanvasState(sessionId, {
        cwd,
        workspace_kind: workspaceKind,
        open,
        activeId,
        docs,
        recent: nextRecent,
      }).catch(() => undefined);
    }, 700);
    return () => {
      if (persistTimer.current) window.clearTimeout(persistTimer.current);
    };
  }, [sessionId, open, activeId, docs, recent, cwd, workspaceKind]);

  const active = useMemo(
    () => docs.find((d) => d.id === activeId) || docs[0] || null,
    [docs, activeId],
  );

  const lastDoc = useMemo(() => {
    if (active) return active;
    if (docs[0]) return docs[0];
    return recent[0] || null;
  }, [active, docs, recent]);

  const hasLast = !!(docs.length || recent.length);

  const openDoc = useCallback((input: OpenCanvasInput) => {
    setDocs((prev) => {
      const next = applyCanvasOpen(prev, input, {
        activeId: activeIdRef.current,
        paneOpen: openRef.current,
      });
      setActiveId(next.activeId);
      setOpen(true);
      setRecent((r) => rememberRecentDocs(r, next.docs));
      return next.docs;
    });
  }, []);

  const applyDocs = useCallback((next: CanvasDoc[], nextActive?: string | null) => {
    if (!next.length) return;
    setDocs(next);
    setActiveId(nextActive || next[0]?.id || null);
    setRecent((r) => rememberRecentDocs(r, next));
  }, []);

  const hydrateOfficeBodies = useCallback(async (list: CanvasDoc[]) => {
    for (const d of list) {
      if (!needsOfficeHydration(d)) continue;
      const id = officeIdFromDoc(d);
      if (!id) continue;
      try {
        const data = await getOfficeOutline(id);
        const outline = data?.outline;
        if (!outline) continue;
        setDocs((prev) =>
          prev.map((row) =>
            row.id === d.id
              ? {
                  ...row,
                  body: JSON.stringify(outline),
                  title: String(outline.title || row.title),
                  updatedAt: new Date().toISOString(),
                }
              : row,
          ),
        );
      } catch {
        /* ignore */
      }
    }
  }, []);

  const hydrateFromDisk = useCallback(async () => {
    if (!sessionId) return;
    const current = docsRef.current;
    if (current.length) {
      await hydrateOfficeBodies(current);
      return;
    }
    try {
      if (cwd && workspaceKind !== "ssh") {
        const snap = await getCanvasState(sessionId, { cwd, workspace_kind: workspaceKind });
        const remoteDocs = normalizeCanvasDocs(snap?.docs);
        const remoteRecent = normalizeCanvasDocs(snap?.recent);
        if (remoteDocs.length || remoteRecent.length) {
          const next = remoteDocs.length ? remoteDocs : remoteRecent;
          applyDocs(next, snap?.activeId || next[0]?.id || null);
          if (remoteRecent.length) setRecent(remoteRecent);
          await hydrateOfficeBodies(next);
          return;
        }
      }
      const listed = await listOfficeRecent({ cwd: cwd || undefined, limit: 4 });
      const first = listed?.items?.[0];
      if (!first?.outline && !first?.doc_id) return;
      const outline = first.outline || first;
      openDoc({
        kind: "office",
        title: first.title || String(outline.title || "Office"),
        body: JSON.stringify(outline),
        dedupeKey: first.doc_id,
        source: first.doc_id,
      });
    } catch {
      /* ignore */
    }
  }, [applyDocs, cwd, hydrateOfficeBodies, openDoc, sessionId, workspaceKind]);

  const closePane = useCallback(() => {
    setRecent((prev) => rememberRecentDocs(prev, docsRef.current));
    setOpen(false);
  }, []);

  const reopenLast = useCallback(() => {
    setDocs((prev) => {
      if (prev.length) {
        setActiveId((id) => id || prev[0].id);
        return prev;
      }
      const rec = recentRef.current;
      if (rec.length) {
        setActiveId(rec[0].id);
        return rec;
      }
      return prev;
    });
    setOpen(true);
    void hydrateFromDisk();
  }, [hydrateFromDisk]);

  const togglePane = useCallback(() => {
    if (openRef.current) {
      closePane();
      return;
    }
    reopenLast();
  }, [closePane, reopenLast]);

  const closeDoc = useCallback((id: string) => {
    setDocs((prev) => {
      const closed = prev.find((d) => d.id === id);
      if (closed) setRecent((r) => archiveCanvasDoc(r, closed));
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
      if (!detail) return;
      if (!detail.body && detail.kind !== "office") return;
      openDoc({ ...detail, body: detail.body || "{}" });
    };
    window.addEventListener(NLM_CANVAS_OPEN_EVENT, onOpen as EventListener);
    return () => window.removeEventListener(NLM_CANVAS_OPEN_EVENT, onOpen as EventListener);
  }, [openDoc]);

  return {
    open,
    setOpen,
    docs,
    recent,
    active,
    activeId,
    lastDoc,
    hasLast,
    openDoc,
    closePane,
    togglePane,
    reopenLast,
    closeDoc,
    selectDoc,
    updateDoc,
    updateActiveBody,
  };
}

export type CanvasSessionApi = ReturnType<typeof useCanvasSession>;
