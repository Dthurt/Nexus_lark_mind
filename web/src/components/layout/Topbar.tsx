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

const PROJECT_GITHUB_URL = "https://github.com/Dthurt/Nexus_lark_mind";

function GithubMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 98 96"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-hidden
    >
      <path
        fill="currentColor"
        fillRule="evenodd"
        clipRule="evenodd"
        d="M48.854 0C21.839 0 0 22 0 49.217c0 21.756 13.993 40.172 33.405 46.69 2.427.49 3.316-1.059 3.316-2.362 0-1.141-.08-5.052-.08-9.127-13.59 2.934-16.42-5.867-16.42-5.867-2.184-5.704-5.42-7.17-5.42-7.17-4.448-3.015.324-3.015.324-3.015 4.934.326 7.523 5.052 7.523 5.052 4.367 7.496 11.404 5.378 14.235 4.074.404-3.178 1.699-5.378 3.074-6.6-10.839-1.141-22.243-5.378-22.243-24.283 0-5.378 1.94-9.778 5.014-13.2-.485-1.222-2.184-6.275.486-13.038 0 0 4.125-1.304 13.426 5.052a46.97 46.97 0 0 1 12.214-1.63c4.125 0 8.33.571 12.213 1.63 9.302-6.356 13.427-5.052 13.427-5.052 2.67 6.763.97 11.816.485 13.038 3.155 3.422 5.015 7.822 5.015 13.2 0 18.905-11.404 23.06-22.324 24.283 1.78 1.548 3.316 4.481 3.316 9.126 0 6.6-.08 11.897-.08 13.526 0 1.304.89 2.853 3.316 2.364 19.412-6.52 33.405-24.935 33.405-46.691C97.707 22 75.788 0 48.854 0z"
      />
    </svg>
  );
}

const THEME_ICON: Record<Theme, LucideIcon> = {
  day: Sun,
  gray: Contrast,
  night: Moon,
  ocean: Waves,
  rose: Flower2,
};

export type TopbarProps = {
  title?: string;
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

      <Button
        asChild
        type="button"
        variant="outline"
        size="icon"
        className="size-8 shrink-0 text-muted-foreground hover:text-foreground"
        title="在 GitHub 打开本项目"
      >
        <a
          href={PROJECT_GITHUB_URL}
          target="_blank"
          rel="noopener noreferrer"
          aria-label="在 GitHub 打开本项目"
        >
          <GithubMark className="size-4" />
        </a>
      </Button>

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
