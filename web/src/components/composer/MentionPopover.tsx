import { useEffect, useMemo, useState } from "react";
import { File, Folder } from "lucide-react";

import { browseSsh, browseWorkspace } from "@/api/endpoints";
import { cn } from "@/lib/utils";
import type { ContextRef } from "@/lib/contextRefs";
import type { BrowseEntry } from "@/types/api";

export type MentionPopoverProps = {
  open: boolean;
  query: string;
  cwd?: string;
  workspaceKind?: string;
  sshHostId?: string;
  onSelect: (ref: ContextRef) => void;
  onClose: () => void;
  className?: string;
};

function relFromCwd(cwd: string, absOrRel: string): string {
  const c = cwd.replace(/\\/g, "/").replace(/\/$/, "");
  const p = absOrRel.replace(/\\/g, "/");
  if (p.toLowerCase().startsWith(c.toLowerCase() + "/")) return p.slice(c.length + 1);
  if (p.toLowerCase() === c.toLowerCase()) return ".";
  return p;
}

export function MentionPopover({
  open,
  query,
  cwd = "",
  workspaceKind = "local",
  sshHostId = "",
  onSelect,
  onClose,
  className,
}: MentionPopoverProps) {
  const [entries, setEntries] = useState<BrowseEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [active, setActive] = useState(0);
  const q = query.trim().toLowerCase();

  useEffect(() => {
    if (!open || !cwd) {
      setEntries([]);
      return;
    }
    let cancelled = false;
    setLoading(true);
    const run = async () => {
      try {
        const data =
          workspaceKind === "ssh" && sshHostId
            ? await browseSsh(sshHostId, cwd)
            : await browseWorkspace(cwd);
        if (cancelled) return;
        setEntries(data?.entries || []);
      } catch {
        if (!cancelled) setEntries([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
  }, [open, cwd, workspaceKind, sshHostId]);

  const filtered = useMemo(() => {
    const rows = entries.filter((e) => {
      const name = String(e.name || e.path || "").toLowerCase();
      return !q || name.includes(q);
    });
    return rows.slice(0, 24);
  }, [entries, q]);

  useEffect(() => {
    setActive(0);
  }, [query, filtered.length]);

  useEffect(() => {
    if (!open) return;
    const onKey = (ev: KeyboardEvent) => {
      if (ev.key === "Escape") {
        ev.preventDefault();
        onClose();
        return;
      }
      if (ev.key === "ArrowDown") {
        ev.preventDefault();
        setActive((i) => Math.min(i + 1, Math.max(0, filtered.length - 1)));
        return;
      }
      if (ev.key === "ArrowUp") {
        ev.preventDefault();
        setActive((i) => Math.max(0, i - 1));
        return;
      }
      if (ev.key === "Enter" && filtered[active]) {
        ev.preventDefault();
        pick(filtered[active]);
      }
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [open, filtered, active, onClose]);

  if (!open) return null;

  function pick(entry: BrowseEntry) {
    const abs = String(entry.path || entry.name || "");
    const path = cwd ? relFromCwd(cwd, abs) : abs;
    const isDir = !!(entry.is_dir ?? entry.is_file === false);
    onSelect({ path: path === "." ? "" : path, kind: isDir ? "dir" : "file", label: entry.name });
  }

  return (
    <div
      className={cn(
        "absolute bottom-full left-2 z-30 mb-1 max-h-56 w-[min(420px,92vw)] overflow-auto rounded-md border border-border bg-popover shadow-lg",
        className,
      )}
      role="listbox"
      aria-label="@ 上下文"
    >
      <div className="border-b border-border/60 px-2 py-1 text-[10px] text-muted-foreground">
        @ 附加到上下文{cwd ? ` · ${cwd}` : " · 先绑定工作区"}
      </div>
      {!cwd ? (
        <p className="m-0 px-2 py-2 text-[11px] text-muted-foreground">绑定工作区后可浏览文件</p>
      ) : loading ? (
        <p className="m-0 px-2 py-2 text-[11px] text-muted-foreground">加载中…</p>
      ) : !filtered.length ? (
        <p className="m-0 px-2 py-2 text-[11px] text-muted-foreground">无匹配</p>
      ) : (
        <ul className="m-0 list-none p-1">
          {filtered.map((e, i) => {
            const isDir = !!(e.is_dir ?? e.is_file === false);
            return (
              <li key={`${e.path}-${i}`}>
                <button
                  type="button"
                  role="option"
                  aria-selected={i === active}
                  className={cn(
                    "flex w-full items-center gap-2 rounded px-2 py-1 text-left text-[12px]",
                    i === active ? "bg-primary/15 text-foreground" : "text-foreground/90 hover:bg-muted/50",
                  )}
                  onMouseEnter={() => setActive(i)}
                  onClick={() => pick(e)}
                >
                  {isDir ? (
                    <Folder className="size-3.5 shrink-0 text-muted-foreground" />
                  ) : (
                    <File className="size-3.5 shrink-0 text-muted-foreground" />
                  )}
                  <span className="min-w-0 truncate font-mono">{e.name || e.path}</span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

export default MentionPopover;
