import { useEffect, useLayoutEffect, useRef, useState, type MouseEvent } from "react";
import { createPortal } from "react-dom";

import { toast } from "sonner";
import {
  disposeEchartsIn,
  enhanceMarkdownRoot,
  renderDrawioIn,
  renderEchartsIn,
  renderMarkdownLight,
  renderMarkdownWithMath,
  renderMathIn,
  renderMermaidIn,
  renderMindmapIn,
  splitSettledMarkdown,
} from "@/lib/markdown";
import {
  loadKnowledgeCitePreview,
  parseKnowledgeCiteHref,
  type KnowledgeCite,
  type KnowledgeCitePreview,
} from "@/lib/kbCite";
import { DEFAULT_LOCAL_KB_ID } from "@/lib/knowledgeScope";
import { rewriteWikiLinks } from "@/lib/wikiLinks";
import { linkifyPlainText } from "@/lib/markdown/linkify";
import { cn } from "@/lib/utils";
import {
  repairDrawio as repairDrawioApi,
  repairEcharts as repairEchartsApi,
  repairMermaid as repairMermaidApi,
} from "@/api/endpoints";

export type MarkdownBodyProps = {
  content?: string;
  streaming?: boolean;
  plain?: boolean;
  kbId?: string;
  modelProvider?: string;
  modelName?: string;
  /** When `fast`, Draw.io fences render as blocked source (no viewer). */
  experienceTier?: "fast" | "balanced" | "high" | string;
  className?: string;
  onMermaidFixed?: (args: { from: string; to: string }) => void;
  onEchartsFixed?: (args: { from: string; to: string }) => void;
  onDrawioFixed?: (args: { from: string; to: string }) => void;
};

type CitePeekState = {
  cite: KnowledgeCite;
  x: number;
  y: number;
  loading: boolean;
  error: string;
  preview: KnowledgeCitePreview | null;
};

function openKnowledgeCite(cite: KnowledgeCite) {
  window.dispatchEvent(new CustomEvent("nlm-knowledge-open", { detail: { href: cite.href } }));
}

function placePeek(el: HTMLElement): { x: number; y: number } {
  const rect = el.getBoundingClientRect();
  const width = Math.min(380, window.innerWidth - 24);
  const x = Math.max(12, Math.min(rect.left, window.innerWidth - width - 12));
  const below = rect.bottom + 8;
  const y = below + 220 > window.innerHeight ? Math.max(12, rect.top - 228) : below;
  return { x, y };
}

const STREAM_LIGHT_MS = 120;

/**
 * Streaming: light-render settled (closed) blocks + plain growing tail.
 * After stream ends: one full markdown / diagram enhance pass.
 */
export function MarkdownBody({
  content = "",
  streaming = false,
  plain = false,
  kbId = "",
  modelProvider = "",
  modelName = "",
  experienceTier = "balanced",
  className,
  onMermaidFixed,
  onEchartsFixed,
  onDrawioFixed,
}: MarkdownBodyProps) {
  const rootRef = useRef<HTMLDivElement>(null);
  const [html, setHtml] = useState("");
  const [streamSettledHtml, setStreamSettledHtml] = useState("");
  const [streamTail, setStreamTail] = useState("");
  const [themeTick, setThemeTick] = useState(0);
  const genRef = useRef(0);
  const streamTimerRef = useRef<number | null>(null);
  const pendingStreamRef = useRef(content);
  const onFixedRef = useRef(onMermaidFixed);
  onFixedRef.current = onMermaidFixed;
  const onEchartsFixedRef = useRef(onEchartsFixed);
  onEchartsFixedRef.current = onEchartsFixed;
  const onDrawioFixedRef = useRef(onDrawioFixed);
  onDrawioFixedRef.current = onDrawioFixed;
  const allowDrawio = String(experienceTier || "balanced").toLowerCase() !== "fast";
  const citedContent = rewriteWikiLinks(content, kbId || DEFAULT_LOCAL_KB_ID);
  const [peek, setPeek] = useState<CitePeekState | null>(null);
  const peekTimerRef = useRef<number | null>(null);
  const hideTimerRef = useRef<number | null>(null);
  const peekGenRef = useRef(0);

  const clearPeekTimers = () => {
    if (peekTimerRef.current != null) {
      window.clearTimeout(peekTimerRef.current);
      peekTimerRef.current = null;
    }
    if (hideTimerRef.current != null) {
      window.clearTimeout(hideTimerRef.current);
      hideTimerRef.current = null;
    }
  };

  const hidePeek = (delay = 160) => {
    if (hideTimerRef.current != null) window.clearTimeout(hideTimerRef.current);
    hideTimerRef.current = window.setTimeout(() => {
      hideTimerRef.current = null;
      peekGenRef.current += 1;
      setPeek(null);
    }, delay);
  };

  const showPeek = (el: HTMLElement, cite: KnowledgeCite) => {
    clearPeekTimers();
    peekTimerRef.current = window.setTimeout(() => {
      peekTimerRef.current = null;
      const pos = placePeek(el);
      const gen = ++peekGenRef.current;
      setPeek({ cite, ...pos, loading: true, error: "", preview: null });
      void loadKnowledgeCitePreview(cite)
        .then((preview) => {
          if (gen !== peekGenRef.current) return;
          setPeek((cur) => (cur && cur.cite.href === cite.href ? { ...cur, loading: false, preview } : cur));
        })
        .catch((err: unknown) => {
          if (gen !== peekGenRef.current) return;
          setPeek((cur) =>
            cur && cur.cite.href === cite.href
              ? { ...cur, loading: false, error: String((err as Error)?.message || err || "原文不可用") }
              : cur,
          );
        });
    }, 180);
  };

  useEffect(() => {
    return () => {
      clearPeekTimers();
      peekGenRef.current += 1;
    };
  }, []);

  const onCiteClick = (event: MouseEvent<HTMLElement>) => {
    const a = (event.target as HTMLElement).closest("a.nlm-kb-cite, a[href]");
    if (!a) return;
    const href = a.getAttribute("href") || "";
    const cite = parseKnowledgeCiteHref(href);
    if (!cite) return;
    event.preventDefault();
    event.stopPropagation();
    clearPeekTimers();
    setPeek(null);
    openKnowledgeCite(cite);
  };

  const onCiteOver = (event: MouseEvent<HTMLElement>) => {
    const a = (event.target as HTMLElement).closest("a.nlm-kb-cite");
    if (!a) return;
    const href = a.getAttribute("href") || "";
    const cite = parseKnowledgeCiteHref(href);
    if (!cite || !cite.slug) return;
    if (hideTimerRef.current != null) {
      window.clearTimeout(hideTimerRef.current);
      hideTimerRef.current = null;
    }
    showPeek(a as HTMLElement, cite);
  };

  const onCiteOut = (event: MouseEvent<HTMLElement>) => {
    const next = event.relatedTarget as Node | null;
    const leaving = (event.target as HTMLElement).closest("a.nlm-kb-cite");
    if (!leaving) return;
    if (next && leaving.contains(next)) return;
    hidePeek();
  };

  const citeBind = {
    "data-kb-id": kbId || undefined,
    onClick: onCiteClick,
    onMouseOver: onCiteOver,
    onMouseOut: onCiteOut,
  };

  const peekNode =
    peek && typeof document !== "undefined"
      ? createPortal(
          <div
            className="nlm-kb-cite-peek"
            style={{ left: peek.x, top: peek.y }}
            role="tooltip"
            data-testid="knowledge-cite-peek"
            onMouseEnter={() => {
              if (hideTimerRef.current != null) {
                window.clearTimeout(hideTimerRef.current);
                hideTimerRef.current = null;
              }
            }}
            onMouseLeave={() => hidePeek(80)}
          >
            <div className="nlm-kb-cite-peek-kicker">
              {peek.cite.kind === "wiki" ? "Wiki 原文" : "知识库原文"}
              {peek.cite.chunkIndex != null ? ` · 分块 #${peek.cite.chunkIndex}` : ""}
            </div>
            <div className="nlm-kb-cite-peek-title">{peek.preview?.title || peek.cite.slug}</div>
            {peek.preview?.heading ? (
              <div className="nlm-kb-cite-peek-heading">{peek.preview.heading}</div>
            ) : null}
            {peek.loading ? (
              <p className="nlm-kb-cite-peek-body is-muted">正在匹配原文…</p>
            ) : peek.error ? (
              <p className="nlm-kb-cite-peek-body is-muted">{peek.error}</p>
            ) : (
              <p className="nlm-kb-cite-peek-body">{peek.preview?.snippet || "没有可预览的原文。"}</p>
            )}
            {peek.preview?.source ? (
              <div className="nlm-kb-cite-peek-source">{peek.preview.source}</div>
            ) : null}
            <button
              type="button"
              className="nlm-kb-cite-peek-open"
              onClick={() => {
                openKnowledgeCite(peek.cite);
                setPeek(null);
              }}
            >
              打开原文
            </button>
          </div>,
          document.body,
        )
      : null;

  useEffect(() => {
    const onTheme = () => setThemeTick((n) => n + 1);
    window.addEventListener("nlm-theme-change", onTheme);
    return () => window.removeEventListener("nlm-theme-change", onTheme);
  }, []);

  // Progressive light markdown while streaming (throttled).
  useEffect(() => {
    if (plain || !streaming) {
      if (streamTimerRef.current != null) {
        window.clearTimeout(streamTimerRef.current);
        streamTimerRef.current = null;
      }
      setStreamSettledHtml("");
      setStreamTail("");
      return;
    }

    pendingStreamRef.current = citedContent;
    const flush = () => {
      streamTimerRef.current = null;
      const { settled, tail } = splitSettledMarkdown(pendingStreamRef.current);
      setStreamSettledHtml(settled ? renderMarkdownLight(settled) : "");
      setStreamTail(tail);
    };

    // Leading paint immediately; coalesce later updates.
    if (streamTimerRef.current == null) {
      const delay = !streamSettledHtml && !streamTail ? 0 : STREAM_LIGHT_MS;
      streamTimerRef.current = window.setTimeout(flush, delay);
    }

    return () => {
      /* keep timer — cancelled when streaming/plain flips */
    };
  }, [citedContent, streaming, plain]);

  // Flush pending stream paint when streaming ends or unmounts.
  useEffect(() => {
    return () => {
      if (streamTimerRef.current != null) {
        window.clearTimeout(streamTimerRef.current);
        streamTimerRef.current = null;
      }
    };
  }, []);

  // Final rich markdown after stream completes.
  useEffect(() => {
    if (plain || streaming) {
      disposeEchartsIn(rootRef.current);
      setHtml("");
      return;
    }

    let cancelled = false;
    const paint = async () => {
      const gen = ++genRef.current;
      const nextHtml = await renderMarkdownWithMath(citedContent, {
        streaming: false,
        allowDrawio,
      });
      if (cancelled || gen !== genRef.current) return;
      disposeEchartsIn(rootRef.current);
      setHtml(nextHtml);
    };

    void paint();
    return () => {
      cancelled = true;
    };
  }, [citedContent, streaming, plain, themeTick, allowDrawio]);

  useLayoutEffect(() => {
    if (plain || streaming || !html) return;
    const root = rootRef.current;
    if (!root) return;

    let cancelled = false;
    const gen = genRef.current;

    enhanceMarkdownRoot(root);

    const modelOpts = {
      model_provider: modelProvider || undefined,
      model_name: modelName || undefined,
    };

    const paintRich = async () => {
      await renderMathIn(root);
      if (cancelled || gen !== genRef.current) return;

      const repairMermaid = async (source: string, error: string) => {
        const data = await repairMermaidApi({ source, error, ...modelOpts });
        return data?.source || "";
      };
      const repairEcharts = async (source: string, error: string) => {
        const data = await repairEchartsApi({ source, error, ...modelOpts });
        return data?.source || "";
      };
      const repairDrawio = async (source: string, error: string) => {
        const data = await repairDrawioApi({ source, error, ...modelOpts });
        return data?.source || "";
      };

      await Promise.all([
        renderMermaidIn(root, {
          streaming: false,
          repair: repairMermaid,
          onFixed: (args) => {
            onFixedRef.current?.(args);
            toast.success("Mermaid 已自动修复语法");
          },
        }),
        renderEchartsIn(root, {
          streaming: false,
          repair: repairEcharts,
          onFixed: (args) => {
            onEchartsFixedRef.current?.(args);
            toast.success("ECharts 已自动修复语法");
          },
        }),
        renderMindmapIn(root),
      ]);
      if (cancelled || gen !== genRef.current) return;
      if (allowDrawio) {
        await renderDrawioIn(root, {
          streaming: false,
          repair: repairDrawio,
          onFixed: (args) => {
            onDrawioFixedRef.current?.(args);
            toast.success("Draw.io 已自动修复语法");
          },
        });
      }
    };

    void paintRich();

    return () => {
      cancelled = true;
      disposeEchartsIn(root);
    };
  }, [html, streaming, plain, modelProvider, modelName, allowDrawio]);

  if (plain) {
    return (
      <>
        <div
          className={cn(
            "nlm-md body min-w-0 max-w-full break-words text-[13.5px] leading-[1.7] plain text-[13px] [&_a]:text-teal [&_a]:underline [&_a]:underline-offset-2",
            className,
          )}
          dangerouslySetInnerHTML={{ __html: linkifyPlainText(citedContent) }}
          {...citeBind}
        />
        {peekNode}
      </>
    );
  }

  if (streaming) {
    return (
      <>
        <div
          className={cn(
            "nlm-md md body min-w-0 max-w-full text-[13.5px] leading-[1.7] break-words [&_*:first-child]:mt-0 [&_*:last-child]:mb-0",
            className,
          )}
          {...citeBind}
        >
          {streamSettledHtml ? (
            <div
              className="nlm-md-settled"
              data-kb-id={kbId || undefined}
              ref={(el) => {
                if (el) enhanceMarkdownRoot(el);
              }}
              dangerouslySetInnerHTML={{ __html: streamSettledHtml }}
            />
          ) : null}
          {streamTail || !streamSettledHtml ? (
            <div
              className="nlm-md-tail break-words [&_a]:text-teal [&_a]:underline"
              dangerouslySetInnerHTML={{
                __html:
                  linkifyPlainText(streamTail || (!streamSettledHtml ? citedContent : "")) +
                  '<span class="streaming-caret" aria-hidden="true"></span>',
              }}
            />
          ) : (
            <span className="streaming-caret" aria-hidden="true" />
          )}
        </div>
        {peekNode}
      </>
    );
  }

  return (
    <>
      <div
        ref={rootRef}
        className={cn(
          "nlm-md md body min-w-0 max-w-full text-[13.5px] leading-[1.7] break-words [&_*:first-child]:mt-0 [&_*:last-child]:mb-0",
          className,
        )}
        dangerouslySetInnerHTML={{ __html: html }}
        {...citeBind}
      />
      {peekNode}
    </>
  );
}

export default MarkdownBody;
