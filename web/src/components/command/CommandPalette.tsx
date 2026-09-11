import { useMemo } from "react";
import {
  Bot,
  Gauge,
  History,
  MessageSquare,
  Moon,
  Plus,
  Puzzle,
  Search,
  Settings,
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
import type { CenterViewId } from "@/components/layout/ViewRing";
import type { LocalConversation } from "@/hooks/useSessions";
import { cycleTheme } from "@/hooks/useTheme";

export type CommandPaletteProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  conversations?: Pick<LocalConversation, "id" | "title">[];
  onNewChat?: () => void;
  onSelectChat?: (id: string) => void;
  onClearChat?: () => void;
  onSetCenterView?: (view: CenterViewId) => void;
  onOpenDockTab?: (tab: "plugins" | "activity" | "usage" | "inspector") => void;
  onToggleTools?: () => void;
  onOpenSettings?: () => void;
  onCycleTheme?: () => void;
};

export function CommandPalette({
  open,
  onOpenChange,
  conversations = [],
  onNewChat,
  onSelectChat,
  onClearChat,
  onSetCenterView,
  onOpenDockTab,
  onToggleTools,
  onOpenSettings,
  onCycleTheme,
}: CommandPaletteProps) {
  const recent = useMemo(() => conversations.slice(0, 8), [conversations]);

  const run = (fn?: () => void) => {
    fn?.();
    onOpenChange(false);
  };

  return (
    <CommandDialog open={open} onOpenChange={onOpenChange}>
      <CommandInput placeholder="搜索命令、会话…" />
      <CommandList>
        <CommandEmpty>无匹配项</CommandEmpty>

        <CommandGroup heading="会话">
          <CommandItem onSelect={() => run(onNewChat)}>
            <Plus className="mr-2 size-4" />
            新对话
            <CommandShortcut>N</CommandShortcut>
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
