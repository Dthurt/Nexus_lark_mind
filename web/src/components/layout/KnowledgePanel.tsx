import { useCallback, useEffect, useState } from "react";
import { BookOpen, FilePlus2, Plus, RefreshCw, Search, Trash2 } from "lucide-react";
import { toast } from "sonner";

import {
  addKnowledgeDoc,
  deleteKnowledgeDoc,
  getKnowledgeDoc,
  getKnowledgeStats,
  getWeknoraHealth,
  listKnowledgeDocs,
  listKnowledgeSyncLog,
  listWeknoraKbs,
  patchKnowledgeDoc,
  reindexKnowledge,
  searchKnowledge,
  syncKnowledgeDocs,
  syncWeknora,
  type KnowledgeDoc,
  type KnowledgeHit,
  type KnowledgeStats,
  type KnowledgeSyncEntry,
  type WeknoraHealth,
  type WeknoraKb,
} from "@/api/endpoints";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

export type KnowledgePanelProps = {
  cwd?: string;
  workspaceId?: string;
  className?: string;
};

export function KnowledgePanel({
  cwd = "",
  workspaceId = "",
  className,
}: KnowledgePanelProps) {
  const [docs, setDocs] = useState<KnowledgeDoc[]>([]);
  const [hits, setHits] = useState<KnowledgeHit[] | null>(null);
  const [stats, setStats] = useState<KnowledgeStats | null>(null);
  const [syncLog, setSyncLog] = useState<KnowledgeSyncEntry[]>([]);
  const [showLog, setShowLog] = useState(false);
  const [query, setQuery] = useState("");
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [filePath, setFilePath] = useState("");
  const [selected, setSelected] = useState<KnowledgeDoc | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [adding, setAdding] = useState(false);
  const [reindexing, setReindexing] = useState(false);
  const [wkHealth, setWkHealth] = useState<WeknoraHealth | null>(null);
  const [wkKbs, setWkKbs] = useState<WeknoraKb[]>([]);
  const [wkKbId, setWkKbId] = useState("");
  const [wkSyncing, setWkSyncing] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [data, st] = await Promise.all([
        listKnowledgeDocs({
          workspace_id: workspaceId || undefined,
          limit: 60,
        }),
        getKnowledgeStats({ workspace_id: workspaceId || undefined }),
      ]);
      setDocs(data.docs || []);
      setStats(st);
      try {
        const health = await getWeknoraHealth();
        setWkHealth(health);
        if (health?.configured && !health?.skipped) {
          const kbs = await listWeknoraKbs(40);
          setWkKbs(kbs.knowledge_bases || []);
          setWkKbId((prev) => prev || kbs.default_kb_id || kbs.knowledge_bases?.[0]?.id || "");
        } else {
          setWkKbs([]);
        }
      } catch {
        setWkHealth(null);
      }
    } catch (err: any) {
      toast.error(String(err?.message || err || "加载失败"));
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  const onWeknoraSync = async () => {
    setWkSyncing(true);
    try {
      const data = await syncWeknora({
        workspace_id: workspaceId || undefined,
        kb_id: wkKbId || undefined,
        direction: "both",
        limit: 40,
      });
      if (data.ok === false) {
        toast.error(String(data.error || "WeKnora 同步失败"));
      } else {
        toast.success("已触发 WeKnora 双向同步");
      }
      await refresh();
    } catch (err: any) {
      toast.error(String(err?.message || err));
    } finally {
      setWkSyncing(false);
    }
  };

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const onSearch = async () => {
    const q = query.trim();
    if (!q) {
      setHits(null);
      return;
    }
    setLoading(true);
    try {
      const data = await searchKnowledge({
        query: q,
        workspace_id: workspaceId || undefined,
        limit: 12,
      });
      setHits(data.results || []);
    } catch (err: any) {
      toast.error(String(err?.message || err));
    } finally {
      setLoading(false);
    }
  };

  const onAdd = async () => {
    const body = content.trim();
    const path = filePath.trim();
    if (!body && !path) {
      toast.error("请粘贴内容或填写工作区相对路径");
      return;
    }
    if (path && !cwd) {
      toast.error("路径导入需要先绑定工作区");
      return;
    }
    setAdding(true);
    try {
      await addKnowledgeDoc({
        title: title.trim() || undefined,
        content: body || undefined,
        path: path || undefined,
        tags: path ? undefined : "manual",
        workspace_id: workspaceId || undefined,
        cwd: cwd || undefined,
      });
      setTitle("");
      setContent("");
      setFilePath("");
      toast.success("已写入知识库");
      setHits(null);
      await refresh();
    } catch (err: any) {
      toast.error(String(err?.message || err));
    } finally {
      setAdding(false);
    }
  };

  const onDelete = async (docId: string) => {
    if (!window.confirm("确认删除该文档？")) return;
    try {
      await deleteKnowledgeDoc(docId);
      if (selected?.doc_id === docId) setSelected(null);
      toast.success("已删除");
      setHits(null);
      await refresh();
    } catch (err: any) {
      toast.error(String(err?.message || err));
    }
  };

  const onOpen = async (docId: string) => {
    try {
      const doc = await getKnowledgeDoc(docId);
      setSelected(doc);
      setEditTitle(doc.title || "");
    } catch (err: any) {
      toast.error(String(err?.message || err));
    }
  };

  const onSaveTitle = async () => {
    if (!selected) return;
    const next = editTitle.trim();
    if (!next || next === selected.title) return;
    try {
      const row = await patchKnowledgeDoc(selected.doc_id, { title: next });
      setSelected(row);
      toast.success("标题已更新");
      await refresh();
    } catch (err: any) {
      toast.error(String(err?.message || err));
    }
  };

  const onSync = async () => {
    if (!cwd) {
      toast.error("请先绑定工作区");
      return;
    }
    setSyncing(true);
    try {
      const data = await syncKnowledgeDocs({
        cwd,
        workspace_id: workspaceId || undefined,
      });
      toast.success(
        `同步完成 · 扫描 ${data.scanned ?? 0} · 新增 ${data.added ?? 0} · 更新 ${data.updated ?? 0}`,
      );
      const log = await listKnowledgeSyncLog({
        workspace_id: workspaceId || undefined,
        limit: 12,
      });
      setSyncLog(log.entries || []);
      setShowLog(true);
      await refresh();
    } catch (err: any) {
      toast.error(String(err?.message || err));
    } finally {
      setSyncing(false);
    }
  };

  const onReindex = async () => {
    setReindexing(true);
    try {
      const data = await reindexKnowledge({
        workspace_id: workspaceId || undefined,
        limit: 200,
      });
      if (data.error) {
        toast.error(data.error);
      } else {
        toast.success(`向量回填 · 更新 ${data.updated ?? 0} / 扫描 ${data.scanned ?? 0}`);
      }
      await refresh();
    } catch (err: any) {
      toast.error(String(err?.message || err));
    } finally {
      setReindexing(false);
    }
  };

  const list = hits ?? docs.map((d) => ({ ...d, score: undefined, snippet: undefined }));

  return (
    <div
      className={cn(
        "flex min-h-0 flex-1 flex-col gap-2 overflow-hidden p-2.5 text-[12px]",
        className,
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-muted-foreground">
            <BookOpen className="size-3" />
            知识库
          </div>
          <p className="m-0 mt-0.5 text-[11px] text-muted-foreground">
            本地 SQLite · 搜索后读取全文
            {stats ? (
              <span className="ml-1 text-foreground/70">
                · {stats.docs} 篇 · {stats.chunks} 块
                {stats.hybrid_ready
                  ? " · hybrid"
                  : stats.embeddings_configured
                    ? " · embed 待回填"
                    : ""}
              </span>
            ) : null}
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap justify-end gap-1">
          {stats?.embeddings_configured ? (
            <Button
              type="button"
              size="sm"
              variant="ghost"
              className="h-7 px-2 text-[11px]"
              disabled={reindexing}
              onClick={() => void onReindex()}
              title="为缺少向量的 chunk 回填 embedding"
            >
              回填向量
            </Button>
          ) : null}
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="h-7 px-2"
            disabled={syncing || !cwd}
            onClick={() => void onSync()}
            title={cwd ? "扫描工作区 docs / md / txt / pdf" : "需要工作区"}
          >
            <RefreshCw className={cn("mr-1 size-3", syncing && "animate-spin")} />
            同步文档
          </Button>
        </div>
      </div>

      {wkHealth && !wkHealth.skipped ? (
        <div className="rounded-md border border-border/60 bg-muted/20 px-2 py-1.5 text-[11px] text-muted-foreground">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="font-medium text-foreground/80">WeKnora</span>
            <span>
              {wkHealth.online
                ? `在线${wkHealth.latency_ms != null ? ` · ${wkHealth.latency_ms}ms` : ""}`
                : wkHealth.error
                  ? `离线 · ${wkHealth.error}`
                  : "未连通"}
            </span>
            {wkHealth.kb_count != null ? <span>· {wkHealth.kb_count} 库</span> : null}
            {wkKbs.length > 0 ? (
              <select
                className="h-6 max-w-[140px] rounded border border-border bg-background px-1 text-[11px]"
                value={wkKbId}
                onChange={(e) => setWkKbId(e.target.value)}
                title="目标知识库"
              >
                {wkKbs.map((kb) => (
                  <option key={kb.id} value={kb.id}>
                    {kb.name || kb.id}
                  </option>
                ))}
              </select>
            ) : null}
            <Button
              type="button"
              size="sm"
              variant="ghost"
              className="h-6 px-1.5 text-[11px]"
              disabled={wkSyncing || !wkKbId}
              onClick={() => void onWeknoraSync()}
            >
              {wkSyncing ? "同步中…" : "双向同步"}
            </Button>
          </div>
        </div>
      ) : wkHealth?.skipped ? (
        <p className="m-0 text-[10px] text-muted-foreground/80">
          WeKnora 未配置（设置 WEKNORA_BASE_URL 后可双向同步）
        </p>
      ) : null}

      <div className="flex gap-1">
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="搜索知识库…"
          className="h-8 text-[12px]"
          onKeyDown={(e) => {
            if (e.key === "Enter") void onSearch();
          }}
        />
        <Button
          type="button"
          size="sm"
          variant="secondary"
          className="h-8 px-2"
          disabled={loading}
          onClick={() => void onSearch()}
        >
          <Search className="size-3.5" />
        </Button>
        {hits ? (
          <Button
            type="button"
            size="sm"
            variant="ghost"
            className="h-8 px-2 text-[11px]"
            onClick={() => {
              setHits(null);
              setQuery("");
            }}
          >
            清除
          </Button>
        ) : null}
      </div>

      <div className="min-h-0 flex-1 space-y-1 overflow-y-auto overscroll-contain">
        {loading && !list.length ? (
          <p className="m-0 text-muted-foreground">加载中…</p>
        ) : null}
        {!loading && !list.length ? (
          <p className="m-0 rounded-md border border-border/60 bg-muted/30 px-2 py-2 text-muted-foreground">
            暂无文档。粘贴 Markdown、填路径导入，或点「同步文档」索引工作区。
          </p>
        ) : null}
        {list.map((row) => {
          const id = row.doc_id;
          return (
            <div
              key={id + (row.chunk_id || "")}
              className={cn(
                "rounded-md border border-border/50 px-2 py-1.5 hover:bg-muted/40",
                selected?.doc_id === id && "border-teal/40 bg-teal/10",
              )}
            >
              <div className="flex items-start justify-between gap-2">
                <button
                  type="button"
                  className="min-w-0 flex-1 text-left"
                  onClick={() => void onOpen(id)}
                >
                  <div className="truncate font-medium text-foreground">
                    {row.title || id}
                    {row.heading ? (
                      <span className="font-normal text-muted-foreground">
                        {" "}
                        · {row.heading}
                      </span>
                    ) : null}
                  </div>
                  <div className="truncate font-mono text-[10px] text-muted-foreground">
                    {row.source_uri || row.source || id}
                    {row.score != null ? ` · score ${row.score}` : ""}
                  </div>
                  {row.snippet ? (
                    <p className="m-0 mt-1 line-clamp-3 text-[11px] text-muted-foreground">
                      {row.snippet}
                    </p>
                  ) : null}
                </button>
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  className="h-7 w-7 shrink-0 p-0 text-muted-foreground hover:text-destructive"
                  title="删除"
                  onClick={() => void onDelete(id)}
                >
                  <Trash2 className="size-3.5" />
                </Button>
              </div>
            </div>
          );
        })}
      </div>

      {selected ? (
        <div className="max-h-[30%] min-h-0 overflow-auto rounded-md border border-border/50 bg-background/40 px-2 py-1.5">
          <div className="mb-1 flex items-center gap-1">
            <Input
              value={editTitle}
              onChange={(e) => setEditTitle(e.target.value)}
              className="h-7 flex-1 text-[11px]"
              onBlur={() => void onSaveTitle()}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  void onSaveTitle();
                }
              }}
            />
            <span className="shrink-0 text-[10px] text-muted-foreground">
              {selected.content_len ?? selected.content?.length ?? 0} chars
            </span>
          </div>
          {selected.source_uri || selected.source ? (
            <div className="mb-1 truncate font-mono text-[10px] text-muted-foreground">
              {selected.source_uri || selected.source}
            </div>
          ) : null}
          <pre className="m-0 whitespace-pre-wrap font-mono text-[10.5px] leading-relaxed text-foreground/90">
            {(selected.content || "").slice(0, 6000)}
            {(selected.content || "").length > 6000 ? "\n…" : ""}
          </pre>
        </div>
      ) : null}

      {showLog && syncLog.length ? (
        <div className="max-h-20 overflow-auto rounded-md border border-border/40 px-2 py-1 text-[10px] text-muted-foreground">
          <div className="mb-0.5 flex items-center justify-between">
            <span className="uppercase tracking-wider">同步日志</span>
            <button
              type="button"
              className="text-[10px] hover:text-foreground"
              onClick={() => setShowLog(false)}
            >
              收起
            </button>
          </div>
          {syncLog.slice(0, 8).map((e) => (
            <div key={`${e.id}-${e.source_uri}`} className="truncate">
              [{e.status}] {e.source_uri || e.source} — {e.message}
            </div>
          ))}
        </div>
      ) : null}

      <div className="shrink-0 space-y-1.5 border-t border-border/60 pt-2">
        <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
          添加
        </div>
        <Input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="标题（可选）"
          className="h-8 text-[12px]"
        />
        <div className="flex gap-1">
          <Input
            value={filePath}
            onChange={(e) => setFilePath(e.target.value)}
            placeholder="或：工作区相对路径 docs/x.md"
            className="h-8 flex-1 font-mono text-[11px]"
            disabled={!cwd}
          />
          <Button
            type="button"
            size="sm"
            variant="secondary"
            className="h-8 shrink-0 px-2"
            disabled={adding || !filePath.trim() || !cwd}
            onClick={() => void onAdd()}
            title="从路径导入"
          >
            <FilePlus2 className="size-3.5" />
          </Button>
        </div>
        <textarea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          placeholder="粘贴 Markdown…"
          rows={3}
          className="w-full resize-y rounded-md border border-input bg-background px-2 py-1.5 font-mono text-[11px] outline-none focus-visible:ring-1 focus-visible:ring-ring"
        />
        <Button
          type="button"
          size="sm"
          className="h-8 w-full"
          disabled={adding || (!content.trim() && !filePath.trim())}
          onClick={() => void onAdd()}
        >
          <Plus className="mr-1 size-3.5" />
          写入知识库
        </Button>
      </div>
    </div>
  );
}

export default KnowledgePanel;
