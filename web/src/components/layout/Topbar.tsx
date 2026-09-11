import type { ComponentProps } from "react";
import {
  Contrast,
  Flower2,
  Moon,
  PanelLeft,
  PanelRight,
  Search,
  Sun,
  Trash2,
  Waves,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { ViewRing, type CenterViewId } from "@/components/layout/ViewRing";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { themeLabel, type Theme, useTheme } from "@/hooks/useTheme";
import { cn } from "@/lib/utils";

const THEME_ICON: Record<Theme, LucideIcon> = {
  day: Sun,
  gray: Contrast,
  night: Moon,
  ocean: Waves,
  rose: Flower2,
};

export type TopbarProps = {
  title?: string;
  sessionId?: string;
  centerView?: CenterViewId;
  onCenterViewChange?: (view: CenterViewId) => void;
  workspaceTitle?: string;
  cwd?: string;
  workspaceKind?: string;
  onToggleSidebar?: () => void;
  onToggleRail?: () => void;
  onClear?: () => void;
  onCycleTheme?: () => void;
  onOpenCommand?: () => void;
  className?: string;
};

export function Topbar({
  title = "新对话",
  sessionId = "",
  centerView = "chat",
  onCenterViewChange,
  workspaceTitle = "",
  cwd = "",
  workspaceKind = "local",
  onToggleSidebar,
  onToggleRail,
  onClear,
  onCycleTheme,
  onOpenCommand,
  className,
}: TopbarProps) {
  const { theme, cycle, label } = useTheme();
  const ThemeIcon = THEME_ICON[theme] ?? Moon;
  const themeTitle = `主题：${label || themeLabel(theme)}（点击切换）`;

  const handleTheme = () => {
    if (onCycleTheme) onCycleTheme();
    else cycle();
  };

  return (
    <header
      className={cn(
        "nlm-topbar flex shrink-0 items-center gap-2 border-b border-border px-4 py-2.5",
        "bg-card/70 backdrop-blur-sm",
        className,
      )}
    >
      <IconButton title="切换左侧栏" aria-label="切换左侧栏" onClick={onToggleSidebar}>
        <PanelLeft className="size-4" />
      </IconButton>

      <div className="flex min-w-0 flex-1 items-baseline gap-2.5">
        <h1 className="m-0 truncate text-sm font-semibold tracking-tight">{title}</h1>
        <div className="flex flex-wrap items-center gap-1.5">
          {cwd ? (
            <code
              title={cwd}
              className="max-w-[220px] truncate rounded border border-teal/35 bg-teal/10 px-1.5 py-0.5 font-mono text-[10px] text-teal"
            >
              {workspaceKind === "ssh" ? "SSH · " : ""}
              {workspaceTitle || cwd}
            </code>
          ) : null}
          {sessionId ? (
            <code className="rounded border border-border bg-muted/40 px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
              {sessionId}
            </code>
          ) : null}
        </div>
      </div>

      <ViewRing
        className="mr-0.5"
        value={centerView}
        onChange={onCenterViewChange}
      />

      <IconButton
        title="命令面板 (Ctrl+K)"
        aria-label="命令面板"
        onClick={onOpenCommand}
        className="hidden sm:inline-flex"
      >
        <Search className="size-4" />
      </IconButton>
      <kbd className="hidden rounded border border-border bg-muted/40 px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground md:inline">
        ⌘K
      </kbd>

      <IconButton title={themeTitle} aria-label={themeTitle} onClick={handleTheme}>
        <ThemeIcon className="size-4" />
      </IconButton>

      <AlertDialog>
        <AlertDialogTrigger asChild>
          <IconButton title="清空当前会话" aria-label="清空当前会话">
            <Trash2 className="size-4" />
          </IconButton>
        </AlertDialogTrigger>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>清空当前会话？</AlertDialogTitle>
            <AlertDialogDescription>
              将清除本会话的消息与轨迹记录，此操作不可撤销。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={() => onClear?.()}>清空</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <IconButton title="切换右侧栏" aria-label="切换右侧栏" onClick={onToggleRail}>
        <PanelRight className="size-4" />
      </IconButton>
    </header>
  );
}

function IconButton({
  children,
  className,
  ...props
}: ComponentProps<typeof Button>) {
  return (
    <Button
      type="button"
      variant="outline"
      size="icon"
      className={cn(
        "size-8 shrink-0 text-muted-foreground hover:text-foreground",
        className,
      )}
      {...props}
    >
      {children}
    </Button>
  );
}

export default Topbar;
