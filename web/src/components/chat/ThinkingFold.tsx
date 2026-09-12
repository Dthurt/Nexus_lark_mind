import { useMemo, useState } from "react";
import { ChevronRight } from "lucide-react";

import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";

export type ThinkingFoldProps = {
  text?: string | null;
  streaming?: boolean;
  className?: string;
};

function flatten(text: string) {
  return text.replace(/\s+/g, " ").trim();
}

/** One-line live window: show the trailing stream while thinking. */
function livePreview(text: string, streaming: boolean, max = 96) {
  const flat = flatten(text);
  if (!flat) return streaming ? "正在思考…" : "";
  if (streaming) {
    // Tail so the line feels like content flowing past.
    return flat.length > max ? `…${flat.slice(-max)}` : flat;
  }
  // Done: show the start as a stable summary.
  return flat.length > max ? `${flat.slice(0, max)}…` : flat;
}

/** Compact, folded reasoning — default collapsed, one-line live preview while streaming. */
export function ThinkingFold({ text, streaming = false, className }: ThinkingFoldProps) {
  const [open, setOpen] = useState(false);
  const body = (text || "").trim();
  if (!body && !streaming) return null;

  const line = useMemo(() => livePreview(body, streaming), [body, streaming]);

  return (
    <Collapsible
      open={open}
      onOpenChange={setOpen}
      className={cn(
        "mb-1.5 w-full max-w-full rounded-md border border-border/60 bg-muted/25 text-[11px] text-muted-foreground",
        className,
      )}
    >
      <CollapsibleTrigger asChild>
        <button
          type="button"
          className="grid w-full grid-cols-[auto_auto_auto_minmax(0,1fr)] items-center gap-1.5 px-2 py-1.5 text-left hover:text-foreground"
        >
          <ChevronRight
            className={cn("size-3 shrink-0 transition-transform", open && "rotate-90")}
            aria-hidden
          />
          <span className="shrink-0 font-medium text-foreground/80">
            {streaming ? "思考中" : "思考过程"}
          </span>
          {streaming ? (
            <span className="size-1.5 shrink-0 animate-pulse rounded-full bg-sky-400/80" aria-hidden />
          ) : (
            <span className="size-1.5 shrink-0" aria-hidden />
          )}
          {!open ? (
            <span
              className={cn(
                "min-w-0 truncate font-mono text-[10.5px] leading-snug opacity-80",
                streaming && "text-foreground/70",
              )}
              title={line}
            >
              {line}
            </span>
          ) : (
            <span className="min-w-0" />
          )}
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <pre className="m-0 max-h-40 overflow-auto whitespace-pre-wrap break-words border-t border-border/50 px-2.5 py-1.5 font-sans text-[11px] leading-relaxed text-muted-foreground">
          {body || (streaming ? "…" : "")}
        </pre>
      </CollapsibleContent>
    </Collapsible>
  );
}

export default ThinkingFold;
