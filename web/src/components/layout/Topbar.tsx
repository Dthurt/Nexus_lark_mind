import type { ComponentProps } from "react";
import {
  Contrast,
  Flower2,
  Moon,
  PanelLeft,
  PanelRight,
  Sun,
  Trash2,
  Waves,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { ViewRing, type CenterViewId } from "@/components/layout/ViewRing";
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

      <IconButton title={themeTitle} aria-label={themeTitle} onClick={handleTheme}>
        <ThemeIcon className="size-4" />
      </IconButton>

      <IconButton title="清空当前会话" aria-label="清空当前会话" onClick={onClear}>
        <Trash2 className="size-4" />
      </IconButton>

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
