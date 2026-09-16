import { useEffect, useMemo, useState } from "react";
import {
  Bot,
  Gauge,
  GitFork,
  History,
  LayoutTemplate,
  MessageSquare,
  Moon,
  Plus,
  Puzzle,
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
import { listSkills } from "@/api/endpoints";
import type { CenterViewId } from "@/components/layout/ViewRing";
import type { LocalConversation } from "@/hooks/useSessions";
import { cycleTheme } from "@/hooks/useTheme";

export type CommandPaletteProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  conversations?: Pick<LocalConversation, "id" | "title">[];
  cwd?: string;
  onNewChat?: () => void;
  onSelectChat?: (id: string) => void;
  onClearChat?: () => void;
  onForkChat?: () => void;
  onInsertText?: (text: string) => void;
  onSetCenterView?: (view: CenterViewId) => void;
  onToggleCanvas?: () => void;
  onNewCanvas?: () => void;
  onOpenDockTab?: (tab: "plugins" | "activity" | "usage" | "inspector") => void;
  onToggleTools?: () => void;
  onOpenSettings?: () => void;
  onCycleTheme?: () => void;
};

export function CommandPalette({
  open,
  onOpenChange,
  conversations = [],
  cwd = "",
  onNewChat,
  onSelectChat,
  onClearChat,
  onForkChat,
  onInsertText,
  onSetCenterView,
  onToggleCanvas,
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

  useEffect(() => {
    if (!open || !cwd) {
      setSkills([]);
      return;
    }
    let cancelled = false;
    void listSkills(cwd)
      .then((data) => {
        if (!cancelled) setSkills(data.skills || []);
      })
      .catch(() => {
        if (!cancelled) setSkills([]);
      });
    return () => {
      cancelled = true;
    };
  }, [open, cwd]);

  const run = (fn?: () => void) => {
    fn?.();
    onOpenChange(false);
  };

  return (
    <CommandDialog open={open} onOpenChange={onOpenChange}>
      <CommandInput placeholder="搜索命令、会话、技能…" />
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
                        `/skill:${s.name}\n请按技能「${s.name}」执行（路径 ${s.path}）。`,
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

        <CommandSeparator />

        <CommandGroup heading="视图">
          <CommandItem onSelect={() => run(() => onSetCenterView?.("chat"))}>
            <MessageSquare className="mr-2 size-4" />
            聊天视图
          </CommandItem>
          <CommandItem onSelect={() => run(() => onSetCenterView?.("trajectory"))}>
            <Bot className="mr-2 size-4" />
            Trajectory 账本
          </CommandItem>
          <CommandItem onSelect={() => run(onToggleCanvas)}>
            <LayoutTemplate className="mr-2 size-4" />
            打开 / 关闭 Canvas
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
