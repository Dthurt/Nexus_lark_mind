import { useEffect, useLayoutEffect, useRef, useState } from "react";

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
  modelProvider?: string;
  modelName?: string;
  className?: string;
  onMermaidFixed?: (args: { from: string; to: string }) => void;
  onEchartsFixed?: (args: { from: string; to: string }) => void;
  onDrawioFixed?: (args: { from: string; to: string }) => void;
};

const STREAM_LIGHT_MS = 120;

/**
 * Streaming: light-render settled (closed) blocks + plain growing tail.
 * After stream ends: one full markdown / diagram enhance pass.
 */
export function MarkdownBody({
  content = "",
  streaming = false,
  plain = false,
  modelProvider = "",
  modelName = "",
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

    pendingStreamRef.current = content;
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
  }, [content, streaming, plain]);

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
      const nextHtml = await renderMarkdownWithMath(content, { streaming: false });
      if (cancelled || gen !== genRef.current) return;
      disposeEchartsIn(rootRef.current);
      setHtml(nextHtml);
    };

    void paint();
    return () => {
      cancelled = true;
    };
  }, [content, streaming, plain, themeTick]);

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
      await renderDrawioIn(root, {
        streaming: false,
        repair: repairDrawio,
        onFixed: (args) => {
          onDrawioFixedRef.current?.(args);
          toast.success("Draw.io 已自动修复语法");
        },
      });
    };

    void paintRich();

    return () => {
      cancelled = true;
      disposeEchartsIn(root);
    };
  }, [html, streaming, plain, modelProvider, modelName]);

  if (plain) {
    return (
      <div
        className={cn(
          "nlm-md body min-w-0 max-w-full whitespace-pre-wrap break-words text-[13.5px] leading-[1.7] plain text-[13px]",
          className,
        )}
      >
        {content}
      </div>
    );
  }

  if (streaming) {
    return (
      <div
        className={cn(
          "nlm-md md body min-w-0 max-w-full text-[13.5px] leading-[1.7] break-words [&_*:first-child]:mt-0 [&_*:last-child]:mb-0",
          className,
        )}
      >
        {streamSettledHtml ? (
          <div
            className="nlm-md-settled"
            dangerouslySetInnerHTML={{ __html: streamSettledHtml }}
          />
        ) : null}
        {streamTail || !streamSettledHtml ? (
          <div className="nlm-md-tail whitespace-pre-wrap break-words">
            {streamTail || (!streamSettledHtml ? content : "")}
            <span className="streaming-caret" aria-hidden="true" />
          </div>
        ) : (
          <span className="streaming-caret" aria-hidden="true" />
        )}
      </div>
    );
  }

  return (
    <div
      ref={rootRef}
      className={cn(
        "nlm-md md body min-w-0 max-w-full text-[13.5px] leading-[1.7] break-words [&_*:first-child]:mt-0 [&_*:last-child]:mb-0",
        className,
      )}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}

export default MarkdownBody;
