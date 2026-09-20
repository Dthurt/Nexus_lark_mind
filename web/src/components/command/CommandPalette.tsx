import { useEffect, useMemo, useState } from "react";
import {
  BookOpen,
  Bookmark,
  Bot,
  FileText,
  Gauge,
  GitFork,
  GitBranch,
  History,
  LayoutTemplate,
  MessageSquare,
  Moon,
  Plus,
  Puzzle,
  RotateCcw,
  Search,
  Settings,
  Sparkles,
  Trash2,
  Wrench,
} from "lucide-react";

import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
  CommandShortcut,
} from "@/components/ui/command";
import {
  getSessionTree,
  listPresets,
  listPrompts,
  listSkills,
  type SessionTreeNode,
} from "@/api/endpoints";
import type { CenterViewId } from "@/components/layout/ViewRing";
import type { LocalConversation } from "@/hooks/useSessions";
import { cycleTheme } from "@/hooks/useTheme";

export type CommandPaletteProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  conversations?: Pick<LocalConversation, "id" | "title">[];
  cwd?: string;
  workspaceId?: string;
  sessionId?: string;
  onNewChat?: () => void;
  onSelectChat?: (id: string) => void;
  onClearChat?: () => void;
  onForkChat?: () => void;
  onReforkChat?: () => void;
  onBookmarkLast?: () => void;
  onInsertText?: (text: string) => void;
  onApplyPreset?: (name: string) => void;
  onClearActiveTools?: () => void;
  onSetCenterView?: (view: CenterViewId) => void;
  onToggleCanvas?: () => void;
  onReopenCanvas?: () => void;
  onNewCanvas?: () => void;
  onOpenDockTab?: (
    tab: "plugins" | "knowledge" | "activity" | "usage" | "inspector",
  ) => void;
  onToggleTools?: () => void;
  onOpenSettings?: () => void;
  onCycleTheme?: () => void;
};

function flattenTree(
  nodes: SessionTreeNode[],
  depth = 0,
): { node: SessionTreeNode; depth: number }[] {
  const out: { node: SessionTreeNode; depth: number }[] = [];
  for (const n of nodes) {
    out.push({ node: n, depth });
    if (n.children?.length) {
      out.push(...flattenTree(n.children, depth + 1));
    }
  }
  return out;
}

export function CommandPalette({
  open,
  onOpenChange,
  conversations = [],
  cwd = "",
  workspaceId = "",
  sessionId = "",
  onNewChat,
  onSelectChat,
  onClearChat,
  onForkChat,
  onReforkChat,
  onBookmarkLast,
  onInsertText,
  onApplyPreset,
  onClearActiveTools,
  onSetCenterView,
  onToggleCanvas,
  onReopenCanvas,
  onNewCanvas,
  onOpenDockTab,
  onToggleTools,
  onOpenSettings,
  onCycleTheme,
}: CommandPaletteProps) {
  const recent = useMemo(() => conversations.slice(0, 8), [conversations]);
  const [skills, setSkills] = useState<
    { name: string; description: string; path: string }[]
  >([]);
  const [prompts, setPrompts] = useState<
    { name: string; description: string; slash?: string; variables?: string[] }[]
  >([]);
  const [presets, setPresets] = useState<
    {
      name: string;
      description: string;
      active_tools?: string[] | null;
      permission_preset?: string;
    }[]
  >([]);
  const [treeRows, setTreeRows] = useState<{ node: SessionTreeNode; depth: number }[]>(
    [],
  );

  useEffect(() => {
    if (!open) {
      setSkills([]);
      setPrompts([]);
      setPresets([]);
      setTreeRows([]);
      return;
    }
    let cancelled = false;
    void listSkills(cwd || "")
      .then((data) => {
        if (!cancelled) setSkills(data.skills || []);
      })
      .catch(() => {
        if (!cancelled) setSkills([]);
      });
    void listPrompts(cwd || "")
      .then((data) => {
        if (!cancelled) setPrompts(data.prompts || []);
      })
      .catch(() => {
        if (!cancelled) setPrompts([]);
      });
    void listPresets(cwd || "")
      .then((data) => {
        if (!cancelled) setPresets(data.presets || []);
      })
      .catch(() => {
        if (!cancelled) setPresets([]);
      });
    void getSessionTree(workspaceId || "")
      .then((data) => {
        if (cancelled) return;
        const flat = flattenTree(data.roots || []);
        // Only show tree strip when there is at least one fork edge
        const hasFork = flat.some((r) => r.depth > 0);
        setTreeRows(hasFork ? flat.slice(0, 24) : []);
      })
      .catch(() => {
        if (!cancelled) setTreeRows([]);
      });
    return () => {
      cancelled = true;
    };
  }, [open, cwd, workspaceId]);

  const run = (fn?: () => void) => {
    fn?.();
    onOpenChange(false);
  };

  return (
    <CommandDialog open={open} onOpenChange={onOpenChange}>
      <CommandInput placeholder="搜索命令、会话、技能、模板、预设…" />
      <CommandList>
        <CommandEmpty>无匹配项</CommandEmpty>

        <CommandGroup heading="会话">
          <CommandItem onSelect={() => run(onNewChat)}>
            <Plus className="mr-2 size-4" />
            新对话
            <CommandShortcut>N</CommandShortcut>
          </CommandItem>
          <CommandItem onSelect={() => run(onForkChat)}>
            <GitFork className="mr-2 size-4" />
            从此会话分叉（Fork）
          </CommandItem>
          {onReforkChat ? (
            <CommandItem onSelect={() => run(onReforkChat)}>
              <RotateCcw className="mr-2 size-4" />
              回到分叉点再试（Refork）
            </CommandItem>
          ) : null}
          {onBookmarkLast ? (
            <CommandItem onSelect={() => run(onBookmarkLast)}>
              <Bookmark className="mr-2 size-4" />
              收藏当前会话最后一条消息
            </CommandItem>
          ) : null}
          <CommandItem onSelect={() => run(onClearChat)}>
            <Trash2 className="mr-2 size-4" />
            清空当前对话
          </CommandItem>
          {recent.map((c) => (
            <CommandItem key={c.id} onSelect={() => run(() => onSelectChat?.(c.id))}>
              <History className="mr-2 size-4" />
              {c.title || "新对话"}
            </CommandItem>
          ))}
        </CommandGroup>

        {treeRows.length > 0 ? (
          <>
            <CommandSeparator />
            <CommandGroup heading="会话树">
              {treeRows.map(({ node, depth }) => (
                <CommandItem
                  key={node.session_id}
                  onSelect={() => run(() => onSelectChat?.(node.session_id))}
                >
                  <GitBranch className="mr-2 size-4 shrink-0" />
                  <span
                    className="flex min-w-0 flex-col"
                    style={{ paddingLeft: Math.min(depth, 6) * 10 }}
                  >
                    <span className="truncate">
                      {depth > 0 ? "↳ " : ""}
                      {node.title || node.session_id}
                      {node.session_id === sessionId ? " · 当前" : ""}
                    </span>
                    {node.bookmarks?.length ? (
                      <span className="truncate text-xs text-muted-foreground">
                        {node.bookmarks.length} bookmark
                        {node.bookmarks[0]?.label
                          ? ` · ${node.bookmarks[0].label}`
                          : ""}
                      </span>
                    ) : null}
                  </span>
                </CommandItem>
              ))}
            </CommandGroup>
          </>
        ) : null}

        {skills.length > 0 ? (
          <>
            <CommandSeparator />
            <CommandGroup heading="Skills">
              {skills.map((s) => (
                <CommandItem
                  key={s.name}
                  onSelect={() =>
                    run(() =>
                      onInsertText?.(
                        `/skill:${s.name}\n请按技能「${s.name}」执行。`,
                      ),
                    )
                  }
                >
                  <Sparkles className="mr-2 size-4" />
                  <span className="flex min-w-0 flex-col">
                    <span>{s.name}</span>
                    <span className="truncate text-xs text-muted-foreground">
                      {s.description}
                    </span>
                  </span>
                </CommandItem>
              ))}
            </CommandGroup>
          </>
        ) : null}

        {prompts.length > 0 ? (
          <>
            <CommandSeparator />
            <CommandGroup heading="Prompt 模板">
              {prompts.map((p) => (
                <CommandItem
                  key={p.name}
                  onSelect={() =>
                    run(() => {
                      const slash = p.slash || `/${p.name}`;
                      const hint = p.variables?.length
                        ? ` ${p.variables.map((v) => `$${v}`).join(" ")}`
                        : "";
                      onInsertText?.(`${slash}${hint}`.trim());
                    })
                  }
                >
                  <FileText className="mr-2 size-4" />
                  <span className="flex min-w-0 flex-col">
                    <span>
                      {p.slash || `/${p.name}`}
                      {p.variables?.length ? (
                        <span className="ml-1 text-xs text-muted-foreground">
                          ({p.variables.join(", ")})
                        </span>
                      ) : null}
                    </span>
                    <span className="truncate text-xs text-muted-foreground">
                      {p.description}
                    </span>
                  </span>
                </CommandItem>
              ))}
            </CommandGroup>
          </>
        ) : null}

        {presets.length > 0 ? (
          <>
            <CommandSeparator />
            <CommandGroup heading="预设 Presets">
              {presets.map((p) => (
                <CommandItem
                  key={p.name}
                  onSelect={() => run(() => onApplyPreset?.(p.name))}
                >
                  <Sparkles className="mr-2 size-4" />
                  <span className="flex min-w-0 flex-col">
                    <span>{p.name}</span>
                    <span className="truncate text-xs text-muted-foreground">
                      {p.description}
                      {p.active_tools?.length
                        ? ` · ${p.active_tools.length} tools`
                        : ""}
                      {p.permission_preset ? ` · ${p.permission_preset}` : ""}
                    </span>
                  </span>
                </CommandItem>
              ))}
              {onClearActiveTools ? (
                <CommandItem onSelect={() => run(onClearActiveTools)}>
                  <Wrench className="mr-2 size-4" />
                  清除工具收敛（恢复全量工具）
                </CommandItem>
              ) : null}
            </CommandGroup>
          </>
        ) : null}

        <CommandSeparator />

        <CommandGroup heading="视图">
          <CommandItem onSelect={() => run(() => onSetCenterView?.("chat"))}>
            <MessageSquare className="mr-2 size-4" />
            聊天视图
          </CommandItem>
          <CommandItem onSelect={() => run(() => onSetCenterView?.("knowledge"))}>
            <BookOpen className="mr-2 size-4" />
            知识库（检索 / 管理）
          </CommandItem>
          <CommandItem onSelect={() => run(() => onSetCenterView?.("trajectory"))}>
            <Bot className="mr-2 size-4" />
            Trajectory 账本
          </CommandItem>
          <CommandItem onSelect={() => run(onToggleCanvas)}>
            <LayoutTemplate className="mr-2 size-4" />
            打开 / 关闭 Canvas
          </CommandItem>
          <CommandItem onSelect={() => run(onReopenCanvas)}>
            <LayoutTemplate className="mr-2 size-4" />
            恢复上次 Canvas 文档
          </CommandItem>
          <CommandItem onSelect={() => run(onNewCanvas)}>
            <Plus className="mr-2 size-4" />
            新建 Markdown Canvas
          </CommandItem>
        </CommandGroup>

        <CommandSeparator />

        <CommandGroup heading="右坞">
          <CommandItem onSelect={() => run(() => onOpenDockTab?.("plugins"))}>
            <Puzzle className="mr-2 size-4" />
            插件
          </CommandItem>
          <CommandItem onSelect={() => run(() => onOpenDockTab?.("knowledge"))}>
            <BookOpen className="mr-2 size-4" />
            右坞 · 知识库（导入 / 同步）
          </CommandItem>
          <CommandItem onSelect={() => run(() => onOpenDockTab?.("activity"))}>
            <Search className="mr-2 size-4" />
            本回合活动
          </CommandItem>
          <CommandItem onSelect={() => run(() => onOpenDockTab?.("usage"))}>
            <Gauge className="mr-2 size-4" />
            用量
          </CommandItem>
          <CommandItem onSelect={() => run(() => onOpenDockTab?.("inspector"))}>
            <Wrench className="mr-2 size-4" />
            检查器
          </CommandItem>
        </CommandGroup>

        <CommandSeparator />

        <CommandGroup heading="系统">
          <CommandItem onSelect={() => run(onToggleTools)}>
            <Wrench className="mr-2 size-4" />
            切换工具开关
          </CommandItem>
          <CommandItem
            onSelect={() =>
              run(() => {
                if (onCycleTheme) onCycleTheme();
                else cycleTheme();
              })
            }
          >
            <Moon className="mr-2 size-4" />
            切换主题
          </CommandItem>
          <CommandItem onSelect={() => run(onOpenSettings)}>
            <Settings className="mr-2 size-4" />
            打开设置
          </CommandItem>
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  );
}
