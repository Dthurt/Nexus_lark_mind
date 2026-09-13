import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { CanvasEditorShell, useSyncedDraft } from "@/components/canvas/CanvasEditorShell";
import { mxfileToOfflineSvg, normalizeDrawioXml } from "@/lib/markdown/drawio";

export type DrawioCanvasEditorProps = {
  source: string;
  onCommit: (body: string) => void;
};

const EDIT_EMBED_REMOTE =
  "https://embed.diagrams.net/?embed=1&proto=json&spin=1&libraries=1&ui=min&nav=1&layers=1&saveAndExit=0&noExitBtn=1&keepmodified=1";

function resolveEditEmbedUrl(): string {
  try {
    const custom = localStorage.getItem("nlm_drawio_embed");
    if (custom) {
      const u = new URL(custom, window.location.origin);
      u.searchParams.set("embed", "1");
      u.searchParams.set("proto", "json");
      u.searchParams.set("libraries", "1");
      u.searchParams.set("saveAndExit", "0");
      u.searchParams.set("noExitBtn", "1");
      return u.pathname + u.search;
    }
  } catch {
    /* ignore */
  }
  return EDIT_EMBED_REMOTE;
}

export function DrawioCanvasEditor({ source, onCommit }: DrawioCanvasEditorProps) {
  const [draft, setDraft] = useSyncedDraft(source);
  const [mode, setMode] = useState<"preview" | "source" | "split">("split");
  const [status, setStatus] = useState("");
  const [statusError, setStatusError] = useState(false);
  const [embedOk, setEmbedOk] = useState(false);
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const offlineRef = useRef<HTMLDivElement>(null);
  const readyRef = useRef(false);
  const draftRef = useRef(draft);
  draftRef.current = draft;

  const postLoad = useCallback((xml: string) => {
    const iframe = iframeRef.current;
    if (!iframe?.contentWindow) return;
    try {
      iframe.contentWindow.postMessage(JSON.stringify({ action: "load", xml }), "*");
    } catch {
      /* ignore */
    }
  }, []);

  const requestExport = useCallback(() => {
    const iframe = iframeRef.current;
    if (!iframe?.contentWindow || !readyRef.current) {
      setStatus("编辑器未就绪 — 用下方源码「应用」");
      setStatusError(true);
      return;
    }
    try {
      iframe.contentWindow.postMessage(
        JSON.stringify({ action: "export", format: "xml", xml: "1" }),
        "*",
      );
      setStatus("正在从编辑器导出…");
      setStatusError(false);
    } catch (err: any) {
      setStatus(String(err?.message || err));
      setStatusError(true);
    }
  }, []);

  useEffect(() => {
    const xml = normalizeDrawioXml(draft);
    if (offlineRef.current) {
      offlineRef.current.innerHTML = mxfileToOfflineSvg(xml);
    }
  }, [draft]);

  useEffect(() => {
    const iframe = iframeRef.current;
    if (!iframe) return;
    readyRef.current = false;
    setEmbedOk(false);

    const onMessage = (ev: MessageEvent) => {
      if (ev.source !== iframe.contentWindow) return;
      let data: any = ev.data;
      if (typeof data === "string") {
        if (data === "ready") {
          readyRef.current = true;
          setEmbedOk(true);
          postLoad(normalizeDrawioXml(draftRef.current));
          return;
        }
        try {
          data = JSON.parse(data);
        } catch {
          return;
        }
      }
      if (!data || typeof data !== "object") return;
      if (data.event === "init") {
        readyRef.current = true;
        setEmbedOk(true);
        postLoad(normalizeDrawioXml(draftRef.current));
      } else if (data.event === "load" || data.event === "rendered") {
        setStatus("");
        setStatusError(false);
      } else if (data.event === "save" || data.event === "export") {
        const xml = String(data.xml || data.data || "").trim();
        if (!xml) return;
        const normalized = normalizeDrawioXml(xml);
        setDraft(normalized);
        onCommit(normalized);
        setStatus(data.event === "save" ? "已保存到 Canvas" : "已从编辑器同步");
        setStatusError(false);
        window.setTimeout(() => setStatus(""), 1400);
      } else if (data.event === "error") {
        setStatus(String(data.message || "Draw.io 错误"));
        setStatusError(true);
      }
    };

    window.addEventListener("message", onMessage);
    iframe.onload = () => {
      window.setTimeout(() => postLoad(normalizeDrawioXml(draftRef.current)), 400);
    };
    iframe.src = resolveEditEmbedUrl();

    return () => {
      window.removeEventListener("message", onMessage);
      iframe.onload = null;
    };
  }, [onCommit, postLoad, setDraft]);

  const apply = () => {
    const next = normalizeDrawioXml(draft);
    if (!next) {
      setStatus("XML 为空");
      setStatusError(true);
      return;
    }
    onCommit(next);
    setDraft(next);
    if (readyRef.current) postLoad(next);
    setStatus("已写回 Canvas");
    setStatusError(false);
    window.setTimeout(() => setStatus(""), 1200);
  };

  const copyFence = async () => {
    try {
      await navigator.clipboard.writeText("```drawio\n" + normalizeDrawioXml(draft).trim() + "\n```");
      setStatus("已复制 fence");
      setStatusError(false);
    } catch (err: any) {
      setStatus(String(err?.message || err));
      setStatusError(true);
    }
  };

  const openExternal = () => {
    const xml = normalizeDrawioXml(draft);
    window.open(
      `https://app.diagrams.net/?splash=0#R${encodeURIComponent(xml)}`,
      "_blank",
      "noopener,noreferrer",
    );
  };

  return (
    <CanvasEditorShell
      kindLabel="Draw.io"
      draft={draft}
      onDraftChange={setDraft}
      onApply={apply}
      status={status || (embedOk ? "" : "加载嵌入编辑器…")}
      statusError={statusError}
      editorMode={mode}
      onEditorModeChange={setMode}
      applyLabel="应用源码"
      extraActions={
        <>
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="h-6 px-2 text-[11px]"
            onClick={requestExport}
            title="从 diagrams.net 嵌入导出 XML 并写回"
          >
            同步编辑器
          </Button>
          <Button type="button" size="sm" variant="ghost" className="h-6 px-2 text-[11px]" onClick={openExternal}>
            外链
          </Button>
          <Button type="button" size="sm" variant="ghost" className="h-6 px-2 text-[11px]" onClick={() => void copyFence()}>
            复制
          </Button>
        </>
      }
    >
      <div className="relative flex min-h-[240px] flex-col">
        <iframe
          ref={iframeRef}
          title="Draw.io Canvas editor"
          className="min-h-[240px] w-full flex-1 border-0 bg-background"
          referrerPolicy="no-referrer"
          sandbox="allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox"
        />
        <div
          ref={offlineRef}
          className="pointer-events-none absolute inset-x-0 bottom-0 max-h-[40%] overflow-auto border-t border-border/40 bg-card/90 p-1 opacity-90"
          hidden={embedOk}
          aria-hidden={embedOk}
        />
      </div>
    </CanvasEditorShell>
  );
}
