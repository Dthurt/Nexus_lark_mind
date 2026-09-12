import { useMemo, useState } from "react";
import { Download, Eye, FileText, Link2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export type ChatFileItem = {
  name?: string;
  path?: string;
  content?: string;
  mime?: string;
  url?: string;
  size?: number;
  viewMode?: "link" | "text" | "preview";
};

export type ChatFileCardProps = {
  item: ChatFileItem;
  className?: string;
};

type ViewMode = "link" | "text" | "preview";

function looksBinary(mime: string, content: string) {
  if (/^(image|audio|video|application\/octet|application\/zip)/i.test(mime)) return true;
  if (/[\x00-\x08\x0e-\x1f]/.test(content.slice(0, 200))) return true;
  return false;
}

function isImage(mime: string, name: string) {
  return /^image\//i.test(mime) || /\.(png|jpe?g|gif|webp|svg)$/i.test(name);
}

export function ChatFileCard({ item, className }: ChatFileCardProps) {
  const name = item.name || item.path?.split(/[/\\]/).pop() || "file";
  const path = item.path || "";
  const mime = item.mime || "text/plain";
  const content = String(item.content || "");
  const href = item.url || (path ? `file://${path}` : "");
  const [mode, setMode] = useState<ViewMode>(item.viewMode || "link");

  const binary = useMemo(() => looksBinary(mime, content), [mime, content]);
  const image = useMemo(() => isImage(mime, name), [mime, name]);

  function download() {
    if (!content && !href) return;
    if (content) {
      const blob = new Blob([content], { type: mime || "text/plain" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = name;
      a.click();
      URL.revokeObjectURL(url);
      return;
    }
    window.open(href, "_blank", "noopener,noreferrer");
  }

  return (
    <div
      className={cn(
        "chat-file-card w-full max-w-[min(100%,560px)] self-start overflow-hidden rounded-lg border border-border/70 bg-card/40",
        className,
      )}
    >
      <div className="flex items-center gap-1.5 border-b border-border/50 px-2 py-1.5">
        <FileText className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
        <span className="min-w-0 flex-1 truncate font-mono text-xs text-foreground/90" title={path || name}>
          {name}
        </span>
        <div className="inline-flex items-center gap-0.5">
          {(
            [
              ["link", Link2, "Link"],
              ["text", FileText, "Text"],
              ["preview", Eye, "Preview"],
            ] as const
          ).map(([key, Icon, label]) => (
            <Button
              key={key}
              type="button"
              variant="ghost"
              size="icon"
              className={cn(
                "size-7 rounded-md text-muted-foreground",
                mode === key && "bg-muted text-foreground",
              )}
              title={label}
              aria-label={label}
              aria-pressed={mode === key}
              onClick={() => setMode(key)}
            >
              <Icon className="size-3.5" />
            </Button>
          ))}
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="size-7 rounded-md text-muted-foreground"
            title="Download"
            aria-label="Download"
            onClick={download}
          >
            <Download className="size-3.5" />
          </Button>
        </div>
      </div>

      <div className="px-2.5 py-2">
        {mode === "link" ? (
          <a
            className="inline-flex max-w-full items-center gap-1.5 truncate font-mono text-sm text-sky-300/90 underline-offset-2 hover:underline"
            href={href || undefined}
            title={path || name}
            onClick={(e) => {
              if (!href || href.startsWith("file:")) {
                e.preventDefault();
              }
            }}
          >
            <Link2 className="size-3.5 shrink-0" />
            <span className="truncate">{path || name}</span>
          </a>
        ) : null}

        {mode === "text" ? (
          binary && !content ? (
            <p className="m-0 text-xs text-muted-foreground">Binary file — switch to Preview or Download.</p>
          ) : (
            <pre className="m-0 max-h-[320px] overflow-auto whitespace-pre-wrap break-words rounded-md border border-border/50 bg-background/40 p-2 font-mono text-[11px] text-muted-foreground">
              {content || "(empty)"}
            </pre>
          )
        ) : null}

        {mode === "preview" ? (
          image && (href || content.startsWith("data:")) ? (
            <img
              src={href || content}
              alt={name}
              className="max-h-[360px] max-w-full rounded-md border border-border/50 object-contain"
            />
          ) : binary ? (
            <div className="rounded-md border border-dashed border-border/60 px-3 py-6 text-center text-xs text-muted-foreground">
              No inline preview for this type ({mime || "unknown"}).
            </div>
          ) : (
            <pre className="m-0 max-h-[360px] overflow-auto whitespace-pre-wrap break-words rounded-md border border-border/50 bg-background/40 p-2 font-mono text-[11px] leading-relaxed text-foreground/85">
              {content || "(empty)"}
            </pre>
          )
        ) : null}
      </div>
    </div>
  );
}

export default ChatFileCard;
