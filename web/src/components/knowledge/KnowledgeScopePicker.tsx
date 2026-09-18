import { BookOpen, Check, ChevronDown, ExternalLink } from "lucide-react";

import type { WeknoraHealth, WeknoraKb } from "@/api/endpoints";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { kbScopeLabel, LOCAL_KB_ID } from "@/lib/knowledgeScope";
import { cn } from "@/lib/utils";

export type KnowledgeScopePickerProps = {
  value?: string;
  name?: string;
  kbs?: WeknoraKb[];
  health?: WeknoraHealth | null;
  disabled?: boolean;
  onChange?: (kbId: string, kbName: string) => void;
  onOpenKnowledge?: () => void;
  className?: string;
};

export function KnowledgeScopePicker({
  value = "",
  name = "",
  kbs = [],
  health = null,
  disabled = false,
  onChange,
  onOpenKnowledge,
  className,
}: KnowledgeScopePickerProps) {
  const boundId = String(value || "").trim();
  const label = kbScopeLabel(boundId, name);
  const remoteReady = Boolean(health?.configured && !health?.skipped);
  const online = Boolean(health?.online);

  return (
    <div className={cn("inline-flex min-w-0 items-center gap-0.5", className)}>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            type="button"
            disabled={disabled}
            title={`知识库：${label}${remoteReady ? (online ? " · WeKnora 在线" : " · WeKnora 离线") : ""}`}
            className={cn(
              "inline-flex max-w-[180px] min-w-0 items-center gap-1 rounded-md border border-transparent px-1.5 py-0.5 text-xs text-muted-foreground",
              "hover:border-border hover:bg-muted hover:text-foreground",
              boundId && "border-teal/35 bg-teal/10 text-teal hover:border-teal/50",
              disabled && "pointer-events-none opacity-50",
            )}
            aria-label={`选择知识库，当前 ${label}`}
          >
            <BookOpen className="size-3 shrink-0" aria-hidden />
            <span className="truncate">{label}</span>
            <ChevronDown className="size-3 shrink-0 opacity-60" aria-hidden />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="z-[80] w-[240px]" side="top" sideOffset={6}>
          <DropdownMenuLabel className="text-[10px] uppercase tracking-wider text-muted-foreground">
            对话绑定的知识库
          </DropdownMenuLabel>
          <DropdownMenuItem
            className="gap-2"
            onSelect={() => onChange?.(LOCAL_KB_ID, "本地知识库")}
          >
            <Check className={cn("size-3.5", boundId ? "opacity-0" : "opacity-100")} />
            <span className="min-w-0 flex-1">本地知识库</span>
            <span className="text-[10px] text-muted-foreground">SQLite</span>
          </DropdownMenuItem>
          {remoteReady ? (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuLabel className="text-[10px] uppercase tracking-wider text-muted-foreground">
                WeKnora{online ? "" : " · 离线"}
              </DropdownMenuLabel>
              {kbs.length ? (
                kbs.map((kb) => {
                  const active = kb.id === boundId;
                  return (
                    <DropdownMenuItem
                      key={kb.id}
                      className="gap-2"
                      onSelect={() => onChange?.(kb.id, kb.name || kb.id)}
                    >
                      <Check className={cn("size-3.5", active ? "opacity-100" : "opacity-0")} />
                      <span className="min-w-0 flex-1 truncate">{kb.name || kb.id}</span>
                      {kb.doc_count != null ? (
                        <span className="text-[10px] text-muted-foreground">{kb.doc_count}</span>
                      ) : null}
                    </DropdownMenuItem>
                  );
                })
              ) : (
                <div className="px-2 py-1.5 text-[11px] text-muted-foreground">
                  {health?.error ? `无法列出知识库 · ${health.error}` : "暂无远程知识库"}
                </div>
              )}
            </>
          ) : (
            <div className="px-2 py-1.5 text-[11px] leading-relaxed text-muted-foreground">
              未配置 WeKnora（WEKNORA_BASE_URL）。对话默认使用本地知识库。
            </div>
          )}
          {onOpenKnowledge ? (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuItem className="gap-2" onSelect={() => onOpenKnowledge()}>
                <ExternalLink className="size-3.5 text-muted-foreground" />
                在知识库中打开
              </DropdownMenuItem>
            </>
          ) : null}
        </DropdownMenuContent>
      </DropdownMenu>
      {onOpenKnowledge ? (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="hidden h-6 px-1.5 text-[10px] text-muted-foreground sm:inline-flex"
          title="打开知识库页面（检索 + 对话）"
          onClick={onOpenKnowledge}
        >
          打开
        </Button>
      ) : null}
    </div>
  );
}

export default KnowledgeScopePicker;
