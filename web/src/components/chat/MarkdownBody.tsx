import { useEffect, useRef, useState } from "react";

import { repairMermaid as repairMermaidApi } from "@/api/endpoints";
import {
  enhanceMarkdownRoot,
  renderDrawioIn,
  renderEchartsIn,
  renderMarkdownWithMath,
  renderMathIn,
  renderMermaidIn,
} from "@/lib/markdown";
import { cn } from "@/lib/utils";

export type MarkdownBodyProps = {
  content?: string;
  streaming?: boolean;
  plain?: boolean;
  modelProvider?: string;
  modelName?: string;
  className?: string;
  onMermaidFixed?: (args: { from: string; to: string }) => void;
};

export function MarkdownBody({
  content = "",
  streaming = false,
  plain = false,
  modelProvider = "",
  modelName = "",
  className,
  onMermaidFixed,
}: MarkdownBodyProps) {
  const rootRef = useRef<HTMLDivElement>(null);
  const [html, setHtml] = useState("");
  const genRef = useRef(0);
  const onFixedRef = useRef(onMermaidFixed);
  onFixedRef.current = onMermaidFixed;

  useEffect(() => {
    if (plain) {
      setHtml("");
      return;
    }

    let cancelled = false;
    let debounceTimer: ReturnType<typeof setTimeout> | null = null;
    const wait = streaming ? 280 : 0;

    const paint = async () => {
      const gen = ++genRef.current;
      const nextHtml = await renderMarkdownWithMath(content, { streaming });
      if (cancelled || gen !== genRef.current) return;
      setHtml(nextHtml);

      // Wait for DOM to commit before enhancing
      await Promise.resolve();
      await Promise.resolve();
      if (cancelled || gen !== genRef.current) return;
      const root = rootRef.current;
      if (!root) return;

      root.querySelectorAll(".echarts-block").forEach((block) => {
        const el = block as HTMLElement & { _nlmChart?: { dispose?: () => void } | null };
        if (el._nlmChart) {
          try {
            el._nlmChart.dispose?.();
          } catch {
            /* ignore */
          }
          el._nlmChart = null;
        }
      });

      enhanceMarkdownRoot(root);
      await renderMathIn(root);

      const repair = streaming
        ? null
        : async (source: string, error: string) => {
            const data = await repairMermaidApi({
              source,
              error,
              model_provider: modelProvider || undefined,
              model_name: modelName || undefined,
            });
            return data?.source || "";
          };

      await Promise.all([
        renderMermaidIn(root, {
          streaming: false,
          repair,
          onFixed: (args) => onFixedRef.current?.(args),
        }),
        renderEchartsIn(root, { streaming }),
      ]);
      if (!streaming) {
        await renderDrawioIn(root, { streaming: false });
      }
    };

    debounceTimer = setTimeout(() => {
      debounceTimer = null;
      void paint();
    }, wait);

    return () => {
      cancelled = true;
      if (debounceTimer) clearTimeout(debounceTimer);
      rootRef.current?.querySelectorAll?.(".echarts-block").forEach((block) => {
        const el = block as HTMLElement & { _nlmChart?: { dispose?: () => void } | null };
        try {
          el._nlmChart?.dispose?.();
        } catch {
          /* ignore */
        }
      });
    };
  }, [content, streaming, plain, modelProvider, modelName]);

  if (plain) {
    return (
      <div className={cn("nlm-md plain whitespace-pre-wrap break-words text-[13px]", className)}>
        {content}
      </div>
    );
  }

  return (
    <div
      ref={rootRef}
      className={cn("nlm-md md body text-[13px] leading-relaxed break-words [&_*:first-child]:mt-0 [&_*:last-child]:mb-0", className)}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}

export default MarkdownBody;
