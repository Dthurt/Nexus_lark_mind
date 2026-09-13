import { useEffect, useRef, useState } from "react";
import { RefreshCw } from "lucide-react";

import type { MarketplaceCatalog, MarketplaceItem } from "@/api/endpoints";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export type MarketplacePanelProps = {
  catalog: MarketplaceCatalog | null;
  loading?: boolean;
  busyId?: string | null;
  onRefresh?: () => void | Promise<void>;
  onInstallPath?: (path: string) => void | Promise<void>;
  onInstallZip?: (file: File) => void | Promise<void>;
  onEnable?: (pluginId: string) => void | Promise<void>;
};

export function MarketplacePanel({
  catalog,
  loading = false,
  busyId = null,
  onRefresh,
  onInstallPath,
  onInstallZip,
  onEnable,
}: MarketplacePanelProps) {
  const [path, setPath] = useState("");
  const [hint, setHint] = useState("");
  const [error, setError] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const items = catalog?.items || [];

  useEffect(() => {
    void onRefresh?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- load once on mount
  }, []);

  async function run(label: string, fn: () => Promise<void>) {
    setError("");
    setHint(`${label}…`);
    try {
      await fn();
      setHint(`${label}完成`);
    } catch (err: any) {
      setError(String(err?.message || err));
      setHint("");
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto overscroll-contain p-2.5">
      <div className="flex items-center justify-between gap-2">
        <p className="m-0 text-[10.5px] text-muted-foreground">本地市场 · 非公开远程目录</p>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-6 px-1.5"
          disabled={loading}
          onClick={() => void onRefresh?.()}
        >
          <RefreshCw className={cn("size-3", loading && "animate-spin")} />
        </Button>
      </div>

      <div className="space-y-1.5 rounded-md border border-border/60 bg-foreground/[0.02] p-2">
        <div className="text-[10px] uppercase tracking-wide text-muted-foreground">从路径安装</div>
        <input
          className="h-7 w-full rounded-md border border-border bg-background px-1.5 font-mono text-[11px]"
          placeholder="plugin_catalog/hello_market 或绝对路径"
          value={path}
          onChange={(e) => setPath(e.target.value)}
        />
        <div className="flex flex-wrap gap-1.5">
          <Button
            type="button"
            size="sm"
            className="h-6 px-2 text-[11px]"
            disabled={!path.trim() || !!busyId}
            onClick={() =>
              void run("安装", async () => {
                await onInstallPath?.(path.trim());
              })
            }
          >
            安装目录
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-6 px-2 text-[11px]"
            disabled={!!busyId}
            onClick={() => fileRef.current?.click()}
          >
            上传 zip
          </Button>
          <input
            ref={fileRef}
            type="file"
            accept=".zip,application/zip"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              e.target.value = "";
              if (!file) return;
              void run("上传安装", async () => {
                await onInstallZip?.(file);
              });
            }}
          />
        </div>
      </div>

      {error ? <p className="m-0 text-[10.5px] text-destructive">{error}</p> : null}
      {hint ? <p className="m-0 text-[10.5px] text-teal">{hint}</p> : null}
      {(catalog?.hints || []).slice(0, 2).map((h, i) => (
        <p key={i} className="m-0 text-[10px] text-muted-foreground">
          {h}
        </p>
      ))}

      <div className="flex flex-col gap-1">
        {items.map((item) => (
          <MarketRow
            key={`${item.source}:${item.id}`}
            item={item}
            busy={busyId === item.id || busyId === item.path}
            onInstall={() =>
              void run(`安装 ${item.name || item.id}`, async () => {
                if (item.path) await onInstallPath?.(item.path);
              })
            }
            onEnable={() =>
              void run(`启用 ${item.id}`, async () => {
                await onEnable?.(item.id);
              })
            }
          />
        ))}
        {!items.length && !loading ? (
          <p className="m-0 text-[10.5px] text-muted-foreground">目录为空</p>
        ) : null}
      </div>
    </div>
  );
}

function MarketRow({
  item,
  busy,
  onInstall,
  onEnable,
}: {
  item: MarketplaceItem;
  busy?: boolean;
  onInstall: () => void;
  onEnable: () => void;
}) {
  return (
    <div className="rounded-md border border-border/60 bg-foreground/[0.02] px-2 py-1.5">
      <div className="flex items-start gap-1.5">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1">
            <span className="truncate text-[12px] font-semibold">{item.name || item.id}</span>
            <Badge variant="outline" className="h-4 px-1 font-mono text-[9.5px]">
              {item.source || "?"}
            </Badge>
            <Badge variant="outline" className="h-4 px-1 font-mono text-[9.5px]">
              {item.kind || "?"}
            </Badge>
            {item.installed ? (
              <Badge variant="outline" className="h-4 border-teal/40 px-1 font-mono text-[9.5px] text-teal">
                已加载
              </Badge>
            ) : null}
          </div>
          <div className="truncate font-mono text-[10px] text-muted-foreground">{item.id}</div>
          {item.description ? (
            <p className="mt-0.5 line-clamp-2 text-[10.5px] text-muted-foreground">{item.description}</p>
          ) : null}
          {item.error ? <p className="mt-0.5 text-[10.5px] text-destructive">{item.error}</p> : null}
        </div>
        <div className="flex shrink-0 flex-col gap-1">
          {item.installable ? (
            <Button
              type="button"
              size="sm"
              className="h-6 px-2 text-[11px]"
              disabled={busy || !!item.error}
              onClick={onInstall}
            >
              {item.installed ? "重装" : "安装"}
            </Button>
          ) : item.action === "enable" && !item.installed ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-6 px-2 text-[11px]"
              disabled={busy}
              onClick={onEnable}
            >
              启用
            </Button>
          ) : item.installed ? (
            <span className="px-1 font-mono text-[10px] text-muted-foreground">OK</span>
          ) : null}
        </div>
      </div>
    </div>
  );
}

export default MarketplacePanel;
