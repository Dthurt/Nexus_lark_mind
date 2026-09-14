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
  if (
    /^(image|audio|video|application\/octet|application\/zip|application\/pdf|application\/msword|application\/vnd\.|application\/x-)/i.test(
      mime,
    )
  ) {
    return true;
  }
  const sample = content.slice(0, 4096);
  // Control chars (except tab/LF/CR) → binary. Avoid base64 heuristics that
  // false-positive on minified JSON / long alphanumeric tokens.
  if (/[\x00-\x08\x0e-\x1f]/.test(sample)) return true;
  return false;
}

function isImage(mime: string, name: string) {
  return /^image\//i.test(mime) || /\.(png|jpe?g|gif|webp|svg)$/i.test(name);
}

function isHttpUrl(url: string) {
  return /^https?:\/\//i.test(url);
}

export function ChatFileCard({ item, className }: ChatFileCardProps) {
  const name = item.name || item.path?.split(/[/\\]/).pop() || "file";
  const path = item.path || "";
  const mime = item.mime || "text/plain";
  const content = String(item.content || "");
  const remoteUrl = item.url && isHttpUrl(item.url) ? item.url : "";
  const binary = useMemo(() => looksBinary(mime, content), [mime, content]);
  const image = useMemo(() => isImage(mime, name), [mime, name]);

  const defaultMode: ViewMode =
    item.viewMode ||
    (remoteUrl ? "link" : content && !binary ? "text" : path ? "link" : "text");
  const [mode, setMode] = useState<ViewMode>(defaultMode);

  function download() {
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
    if (remoteUrl) {
      window.open(remoteUrl, "_blank", "noopener,noreferrer");
    }
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
              ["link", Link2, "路径"],
              ["text", FileText, "文本"],
              ["preview", Eye, "预览"],
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
            title="下载"
            aria-label="下载"
            disabled={!content && !remoteUrl}
            onClick={download}
          >
            <Download className="size-3.5" />
          </Button>
        </div>
      </div>

      <div className="px-2.5 py-2">
        {mode === "link" ? (
          remoteUrl ? (
            <a
              className="inline-flex max-w-full items-center gap-1.5 truncate font-mono text-sm text-sky-800 underline-offset-2 hover:underline dark:text-sky-300/90"
              href={remoteUrl}
              title={path || name}
              target="_blank"
              rel="noopener noreferrer"
            >
              <Link2 className="size-3.5 shrink-0" />
              <span className="truncate">{path || name || remoteUrl}</span>
            </a>
          ) : (
            <div
              className="inline-flex max-w-full items-center gap-1.5 truncate font-mono text-sm text-muted-foreground"
              title={path || name}
            >
              <Link2 className="size-3.5 shrink-0 opacity-70" />
              <span className="truncate">{path || name || "（无路径）"}</span>
              {path ? (
                <span className="shrink-0 text-[10px] text-muted-foreground/80">本地路径不可在浏览器中打开</span>
              ) : null}
            </div>
          )
        ) : null}

        {mode === "text" ? (
          binary && !content ? (
            <p className="m-0 text-xs text-muted-foreground">二进制文件 — 请切换到预览或下载。</p>
          ) : (
            <pre className="m-0 max-h-[320px] overflow-auto whitespace-pre-wrap break-words rounded-md border border-border/50 bg-background/40 p-2 font-mono text-[11px] text-muted-foreground">
              {content || "（空）"}
            </pre>
          )
        ) : null}

        {mode === "preview" ? (
          image && (remoteUrl || content.startsWith("data:")) ? (
            <img
              src={remoteUrl || content}
              alt={name}
              className="max-h-[360px] max-w-full rounded-md border border-border/50 object-contain"
            />
          ) : binary ? (
            <div className="rounded-md border border-dashed border-border/60 px-3 py-6 text-center text-xs text-muted-foreground">
              此类型暂无内联预览（{mime || "unknown"}）。
            </div>
          ) : (
            <pre className="m-0 max-h-[360px] overflow-auto whitespace-pre-wrap break-words rounded-md border border-border/50 bg-background/40 p-2 font-mono text-[11px] leading-relaxed text-foreground/85">
              {content || "（空）"}
            </pre>
          )
        ) : null}
      </div>
    </div>
  );
}

export default ChatFileCard;
