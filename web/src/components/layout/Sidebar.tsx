import { useMemo, useState } from "react";
import { Plus, Settings, X } from "lucide-react";
import { motion } from "motion/react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { LocalConversation } from "@/hooks/useSessions";
import { usePrefersReducedMotion } from "@/lib/motion";
import type { Workspace } from "@/types/api";
import { cn } from "@/lib/utils";

export type SidebarConversation = Pick<
  LocalConversation,
  "id" | "title" | "preview" | "cwd" | "workspaceTitle"
> &
  Partial<Pick<LocalConversation, "updatedAt" | "workspaceId" | "workspaceKind" | "sshHostId">>;

export type SidebarWorkspace = Pick<Workspace, "id" | "path"> &
  Partial<Pick<Workspace, "title" | "kind" | "ssh_host_id">>;

export type SidebarProps = {
  conversations?: SidebarConversation[];
  workspaces?: SidebarWorkspace[];
  activeId?: string | null;
  status?: string;
  onNew?: () => void;
  onSelect?: (id: string) => void;
  onDelete?: (id: string) => void;
  onOpenWorkspace?: (workspace: SidebarWorkspace) => void;
  onOpenSettings?: () => void;
  className?: string;
};

export function Sidebar({
  conversations = [],
  workspaces = [],
  activeId,
  status = "ready",
  onNew,
  onSelect,
  onDelete,
  onOpenWorkspace,
  onOpenSettings,
  className,
}: SidebarProps) {
  const [query, setQuery] = useState("");
  const reduced = usePrefersReducedMotion();

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return conversations;
    return conversations.filter((c) => {
      const hay = `${c.title || ""} ${c.preview || ""} ${c.cwd || ""} ${c.workspaceTitle || ""}`.toLowerCase();
      return hay.includes(q);
    });
  }, [conversations, query]);

  return (
    <aside
      className={cn(
        "nlm-sidebar flex h-full min-h-0 flex-col gap-2.5 overflow-hidden border-r border-border bg-[var(--sidebar-bg)] px-3 py-3.5 backdrop-blur-md",
        className,
      )}
    >
      <div className="shrink-0">
        <div className="bg-gradient-to-br from-foreground via-primary to-teal bg-clip-text text-[15px] font-bold tracking-tight text-transparent">
          Nexus Lark Mind
        </div>
        <p className="m-0 mt-0.5 text-[10.5px] uppercase tracking-[0.06em] text-muted-foreground">
          Agent Console
        </p>
      </div>

      <Button
        type="button"
        className="h-8 w-full justify-start gap-1.5 border border-primary/35 bg-primary/15 text-foreground hover:bg-primary/25"
        variant="secondary"
        size="sm"
        onClick={onNew}
      >
        <Plus className="size-3.5" />
        新对话
      </Button>

      <div className="mt-1 shrink-0 text-[10.5px] tracking-wide text-muted-foreground">
        工作目录
      </div>
      <div className="flex max-h-[120px] shrink-0 flex-col gap-1 overflow-auto overscroll-contain px-0.5">
        {workspaces.length === 0 ? (
          <div className="px-0.5 py-1 text-[11px] text-muted-foreground">
            在空对话中添加 Workspace
          </div>
        ) : (
          workspaces.map((w) => (
            <button
              key={w.id}
              type="button"
              title={w.path}
              className="rounded-lg border border-border bg-foreground/[0.03] px-2 py-1.5 text-left transition-colors hover:border-primary/40"
              onClick={() => onOpenWorkspace?.(w)}
            >
              <span className="block truncate text-xs">{w.title || w.path}</span>
            </button>
          ))
        )}
      </div>

      <div className="mt-1 shrink-0 text-[10.5px] tracking-wide text-muted-foreground">
        历史记录
      </div>
      <Input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="搜索会话…"
        className="h-7 shrink-0 bg-background/50 text-[11px]"
      />
      <ScrollArea className="min-h-0 flex-1">
        <div className="flex flex-col gap-1 pr-1">
          {filtered.length === 0 ? (
            <div className="px-2 py-2 text-[11px] text-muted-foreground">
              {query.trim() ? "无匹配会话" : "暂无历史"}
            </div>
          ) : (
            filtered.map((c, i) => {
              const active = c.id === activeId;
              const preview = c.cwd ? c.workspaceTitle || c.cwd : c.preview || "";
              return (
                <motion.button
                  key={c.id}
                  type="button"
                  initial={reduced ? false : { opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: reduced ? 0 : Math.min(i, 8) * 0.02, duration: 0.15 }}
                  className={cn(
                    "group grid w-full grid-cols-[1fr_auto] gap-x-1.5 gap-y-1 rounded-lg border border-transparent px-2.5 py-2 text-left transition-colors",
                    "hover:bg-foreground/[0.04]",
                    active && "border-primary/30 bg-primary/15",
                  )}
                  onClick={() => onSelect?.(c.id)}
                >
                  <span className="truncate text-xs font-medium">{c.title || "新对话"}</span>
                  <span
                    role="button"
                    tabIndex={0}
                    title="删除"
                    className="opacity-0 transition-opacity group-hover:opacity-100"
                    onClick={(e) => {
                      e.stopPropagation();
                      onDelete?.(c.id);
                    }}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        e.stopPropagation();
                        onDelete?.(c.id);
                      }
                    }}
                  >
                    <X className="size-3.5 text-muted-foreground hover:text-destructive" />
                  </span>
                  {preview ? (
                    <span className="col-span-2 truncate text-[10.5px] text-muted-foreground">
                      {preview}
                    </span>
                  ) : null}
                </motion.button>
              );
            })
          )}
        </div>
      </ScrollArea>

      <div className="flex shrink-0 items-center justify-between gap-2 border-t border-border pt-2 text-[10.5px] text-muted-foreground">
        <button
          type="button"
          className="inline-flex items-center gap-1 hover:text-foreground"
          onClick={onOpenSettings}
        >
          <Settings className="size-3" />
          设置
        </button>
        <span className="truncate font-mono">{status}</span>
      </div>
    </aside>
  );
}

export default Sidebar;
