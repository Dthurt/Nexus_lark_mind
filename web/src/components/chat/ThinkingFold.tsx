import { useState } from "react";
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

/** Compact, folded reasoning / chain-of-thought — default collapsed. */
export function ThinkingFold({ text, streaming = false, className }: ThinkingFoldProps) {
  const [open, setOpen] = useState(false);
  const body = (text || "").trim();
  if (!body && !streaming) return null;

  const preview = body.replace(/\s+/g, " ").slice(0, 72);

  return (
    <Collapsible
      open={open}
      onOpenChange={setOpen}
      className={cn(
        "mb-1.5 w-fit max-w-full rounded-md border border-border/60 bg-muted/25 text-[11px] text-muted-foreground",
        className,
      )}
    >
      <CollapsibleTrigger asChild>
        <button
          type="button"
          className="inline-flex max-w-full items-center gap-1 px-2 py-1 text-left hover:text-foreground"
        >
          <ChevronRight
            className={cn("size-3 shrink-0 transition-transform", open && "rotate-90")}
            aria-hidden
          />
          <span className="shrink-0 font-medium text-foreground/75">思考过程</span>
          {streaming ? (
            <span className="size-2 shrink-0 animate-pulse rounded-full bg-sky-400/70" aria-hidden />
          ) : null}
          {!open && preview ? (
            <span className="min-w-0 truncate opacity-70">{preview}{body.length > 72 ? "…" : ""}</span>
          ) : null}
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <pre className="m-0 max-h-36 overflow-auto whitespace-pre-wrap break-words border-t border-border/50 px-2.5 py-1.5 font-sans text-[11px] leading-relaxed text-muted-foreground">
          {body || (streaming ? "…" : "")}
        </pre>
      </CollapsibleContent>
    </Collapsible>
  );
}

export default ThinkingFold;
