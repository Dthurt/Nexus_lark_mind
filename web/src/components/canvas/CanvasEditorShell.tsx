import { useEffect, useId, useRef, useState, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export type CanvasEditorShellProps = {
  kindLabel: string;
  draft: string;
  onDraftChange: (v: string) => void;
  onApply: () => void;
  status?: string;
  statusError?: boolean;
  editorMode?: "preview" | "source" | "split";
  onEditorModeChange?: (m: "preview" | "source" | "split") => void;
  showModes?: boolean;
  applyLabel?: string;
  extraActions?: ReactNode;
  children: ReactNode;
  className?: string;
};

/** Shared chrome: mode switch + source textarea + apply for Canvas P2 editors. */
export function CanvasEditorShell({
  kindLabel,
  draft,
  onDraftChange,
  onApply,
  status = "",
  statusError = false,
  editorMode = "split",
  onEditorModeChange,
  showModes = true,
  applyLabel = "应用",
  extraActions,
  children,
  className,
}: CanvasEditorShellProps) {
  const taId = useId();
  const showPreview = editorMode === "preview" || editorMode === "split";
  const showSource = editorMode === "source" || editorMode === "split";

  return (
    <div className={cn("flex min-h-0 flex-1 flex-col overflow-hidden", className)}>
      <div className="flex shrink-0 flex-wrap items-center gap-1 border-b border-border/50 px-2 py-1">
        <span className="text-[10px] uppercase tracking-wider text-muted-foreground">{kindLabel}</span>
        {showModes && onEditorModeChange ? (
          <span className="ml-1 inline-flex rounded-md border border-border/70 p-0.5">
            {(
              [
                ["split", "分栏"],
                ["preview", "预览"],
                ["source", "源码"],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                type="button"
                className={cn(
                  "rounded px-1.5 py-0.5 text-[10px]",
                  editorMode === id
                    ? "bg-primary/15 text-foreground"
                    : "text-muted-foreground hover:text-foreground",
                )}
                onClick={() => onEditorModeChange(id)}
              >
                {label}
              </button>
            ))}
          </span>
        ) : null}
        {status ? (
          <span
            className={cn(
              "ml-1 max-w-[160px] truncate text-[10px]",
              statusError ? "text-destructive" : "text-muted-foreground",
            )}
            title={status}
          >
            {status}
          </span>
        ) : null}
        <div className="ml-auto flex items-center gap-1">
          {extraActions}
          <Button type="button" size="sm" variant="secondary" className="h-6 px-2 text-[11px]" onClick={onApply}>
            {applyLabel}
          </Button>
        </div>
      </div>

      <div
        className={cn(
          "grid min-h-0 flex-1 overflow-hidden",
          showPreview && showSource ? "grid-rows-2" : "grid-rows-1",
        )}
      >
        {showPreview ? <div className="min-h-0 overflow-auto border-b border-border/40">{children}</div> : null}
        {showSource ? (
          <div className="flex min-h-0 flex-col overflow-hidden p-1.5">
            <label htmlFor={taId} className="sr-only">
              {kindLabel} 源码
            </label>
            <textarea
              id={taId}
              value={draft}
              onChange={(e) => onDraftChange(e.target.value)}
              spellCheck={false}
              className={cn(
                "min-h-0 flex-1 resize-none rounded-md border border-border/70 bg-background/80",
                "px-2 py-1.5 font-mono text-[11px] leading-relaxed text-foreground",
                "outline-none focus-visible:ring-1 focus-visible:ring-ring",
              )}
            />
          </div>
        ) : null}
      </div>
    </div>
  );
}

export function useSyncedDraft(source: string) {
  const [draft, setDraft] = useState(source);
  const prev = useRef(source);
  useEffect(() => {
    if (source !== prev.current) {
      prev.current = source;
      setDraft(source);
    }
  }, [source]);
  return [draft, setDraft] as const;
}
