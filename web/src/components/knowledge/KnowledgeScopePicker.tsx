import { BookOpen, Check, ChevronDown, ExternalLink } from "lucide-react";

import type { LocalKnowledgeBase, WeknoraHealth, WeknoraKb } from "@/api/endpoints";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { DEFAULT_LOCAL_KB_ID, kbScopeLabel, LOCAL_KB_ID } from "@/lib/knowledgeScope";
import { cn } from "@/lib/utils";

export type KnowledgeScopePickerProps = {
  value?: string;
  name?: string;
  kbs?: WeknoraKb[];
  localKbs?: LocalKnowledgeBase[];
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
  localKbs = [],
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
  const extras = localKbs.filter((kb) => kb.id && kb.id !== DEFAULT_LOCAL_KB_ID);
  const defaultLocal = localKbs.find((kb) => kb.id === DEFAULT_LOCAL_KB_ID);
  const localActive = !boundId || boundId === DEFAULT_LOCAL_KB_ID;

  return (
    <div className={cn("inline-flex min-w-0 items-center gap-0.5", className)}>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            type="button"
            disabled={disabled}
            data-testid="knowledge-scope-picker"
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
        <DropdownMenuContent align="start" className="z-[80] w-[260px]" side="top" sideOffset={6}>
          <DropdownMenuLabel className="text-[10px] uppercase tracking-wider text-muted-foreground">
            本地知识库
          </DropdownMenuLabel>
          <DropdownMenuItem
            className="gap-2"
            data-testid="knowledge-scope-local"
            onSelect={() => onChange?.(LOCAL_KB_ID, defaultLocal?.name || "本地知识库")}
          >
            <Check className={cn("size-3.5", localActive ? "opacity-100" : "opacity-0")} />
            <span className="min-w-0 flex-1">{defaultLocal?.name || "本地知识库"}</span>
            <span className="text-[10px] text-muted-foreground">
              {defaultLocal?.doc_count != null ? defaultLocal.doc_count : "SQLite"}
            </span>
          </DropdownMenuItem>
          {extras.map((kb) => {
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
          })}
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
              未配置 WeKnora。多库、拖拽导入、URL 与分块编辑都在本地完成。
            </div>
          )}
          {onOpenKnowledge ? (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                className="gap-2"
                data-testid="knowledge-scope-open-page"
                onSelect={() => onOpenKnowledge()}
              >
                <ExternalLink className="size-3.5 text-muted-foreground" />
                打开知识库
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
          data-testid="composer-open-knowledge"
          className="h-6 shrink-0 px-1.5 text-[11px] text-teal hover:bg-teal/10 hover:text-teal"
          title="打开知识库（检索与管理文档）"
          onClick={onOpenKnowledge}
        >
          打开知识库
        </Button>
      ) : null}
    </div>
  );
}

export default KnowledgeScopePicker;
