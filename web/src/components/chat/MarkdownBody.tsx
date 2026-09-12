import { useEffect, useRef, useState } from "react";

import { toast } from "sonner";
import {
  disposeEchartsIn,
  enhanceMarkdownRoot,
  renderDrawioIn,
  renderEchartsIn,
  renderMarkdownWithMath,
  renderMathIn,
  renderMermaidIn,
  renderMindmapIn,
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
  const [themeTick, setThemeTick] = useState(0);
  const genRef = useRef(0);
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

  useEffect(() => {
    if (plain) {
      setHtml("");
      return;
    }

    let cancelled = false;
    let debounceTimer: ReturnType<typeof setTimeout> | null = null;
    const wait = streaming ? 60 : 0;

    const paint = async () => {
      const gen = ++genRef.current;
      const nextHtml = await renderMarkdownWithMath(content, { streaming });
      if (cancelled || gen !== genRef.current) return;

      // Dispose live charts BEFORE React replaces innerHTML (prevents zr `.get` crashes)
      disposeEchartsIn(rootRef.current);
      setHtml(nextHtml);

      // Wait for DOM to commit before enhancing
      await Promise.resolve();
      await Promise.resolve();
      if (cancelled || gen !== genRef.current) return;
      const root = rootRef.current;
      if (!root) return;

      enhanceMarkdownRoot(root);
      await renderMathIn(root);

      const modelOpts = {
        model_provider: modelProvider || undefined,
        model_name: modelName || undefined,
      };

      const repairMermaid = streaming
        ? null
        : async (source: string, error: string) => {
            const data = await repairMermaidApi({ source, error, ...modelOpts });
            return data?.source || "";
          };

      const repairEcharts = streaming
        ? null
        : async (source: string, error: string) => {
            const data = await repairEchartsApi({ source, error, ...modelOpts });
            return data?.source || "";
          };

      const repairDrawio = streaming
        ? null
        : async (source: string, error: string) => {
            const data = await repairDrawioApi({ source, error, ...modelOpts });
            return data?.source || "";
          };

      await Promise.all([
        renderMermaidIn(root, {
          streaming,
          repair: repairMermaid,
          onFixed: (args) => {
            onFixedRef.current?.(args);
            toast.success("Mermaid 已自动修复语法");
          },
        }),
        renderEchartsIn(root, {
          streaming,
          repair: repairEcharts,
          onFixed: (args) => {
            onEchartsFixedRef.current?.(args);
            toast.success("ECharts 已自动修复语法");
          },
        }),
        renderMindmapIn(root),
      ]);
      if (!streaming) {
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

    debounceTimer = setTimeout(() => {
      debounceTimer = null;
      void paint();
    }, wait);

    return () => {
      cancelled = true;
      if (debounceTimer) clearTimeout(debounceTimer);
      disposeEchartsIn(rootRef.current);
    };
  }, [content, streaming, plain, modelProvider, modelName, themeTick]);

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
      className={cn(
        "nlm-md md body text-[13.5px] leading-[1.7] break-words [&_*:first-child]:mt-0 [&_*:last-child]:mb-0",
        className,
      )}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}

export default MarkdownBody;
