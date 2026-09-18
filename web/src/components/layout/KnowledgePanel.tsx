import { useCallback, useEffect, useState } from "react";
import { BookOpen, FilePlus2, Plus, RefreshCw, Search, Trash2 } from "lucide-react";
import { toast } from "sonner";

import {
  addKnowledgeDoc,
  deleteKnowledgeDoc,
  getKnowledgeDoc,
  getKnowledgeStats,
  getSession,
  getWeknoraHealth,
  listKnowledgeDocs,
  listKnowledgeSyncLog,
  listWeknoraKbs,
  importWeknoraKnowledge,
  listWeknoraKnowledge,
  patchInteraction,
  patchKnowledgeDoc,
  reindexKnowledge,
  searchKnowledge,
  searchWeknora,
  syncKnowledgeDocs,
  syncWeknora,
  type KnowledgeDoc,
  type KnowledgeHit,
  type KnowledgeStats,
  type KnowledgeSyncEntry,
  type WeknoraHealth,
  type WeknoraHit,
  type WeknoraKb,
  type WeknoraKnowledgeItem,
} from "@/api/endpoints";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

export type KnowledgePanelProps = {
  cwd?: string;
  workspaceId?: string;
  sessionId?: string;
  className?: string;
  onBoundKbChange?: (kbId: string, kbName?: string) => void;
};

export function KnowledgePanel({
  cwd = "",
  workspaceId = "",
  sessionId = "",
  className,
  onBoundKbChange,
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
  const [importingId, setImportingId] = useState("");
  const [browseMode, setBrowseMode] = useState<"local" | "remote">("local");
  const [remoteHits, setRemoteHits] = useState<
    Array<WeknoraHit & { doc_id?: string; content?: string }> | null
  >(null);

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
          let sessionKb = "";
          if (sessionId) {
            try {
              const sess = await getSession(sessionId);
              sessionKb = String(sess?.weknora_kb_id || "").trim();
            } catch {
              /* ignore */
            }
          }
          setWkKbId(sessionKb);
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
  }, [workspaceId, sessionId]);

  const onSelectWeknoraKb = async (kbId: string) => {
    const id = String(kbId || "").trim();
    setWkKbId(id);
    const kbName = id
      ? wkKbs.find((kb) => kb.id === id)?.name || id
      : "本地知识库";
    onBoundKbChange?.(id, kbName);
    if (!sessionId) return;
    try {
      if (!id) {
        await patchInteraction(sessionId, { clear_weknora_kb_id: true });
        setBrowseMode("local");
        setRemoteHits(null);
        toast.success("已切换到本地知识库");
        return;
      }
      await patchInteraction(sessionId, { weknora_kb_id: id });
      toast.success("已绑定会话知识库");
    } catch (err: any) {
      toast.error(String(err?.message || err || "绑定 KB 失败"));
    }
  };

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

  const loadRemoteBrowse = async (q: string) => {
    if (!wkKbId) {
      toast.error("请先选择 WeKnora KB");
      return;
    }
    if (!q) {
      const data = await listWeknoraKnowledge({
        kb_id: wkKbId,
        page_size: 40,
      });
      if (data.ok === false && data.error) {
        toast.error(String(data.error));
        setRemoteHits([]);
        return;
      }
      const items = (data.items || []).map((row: WeknoraKnowledgeItem) => ({
        doc_id: row.id,
        title: row.title || row.id,
        snippet: (row.content || "").slice(0, 240),
        content: row.content,
        source_uri: row.id,
        source: "weknora",
        kb_id: wkKbId,
      }));
      setRemoteHits(items);
      return;
    }
    const data = await searchWeknora({
      query: q,
      kb_id: wkKbId,
      weknora_kb_id: wkKbId,
      workspace_id: workspaceId || undefined,
      limit: 12,
    });
    if (data.ok === false && data.error) {
      toast.error(String(data.error));
      setRemoteHits([]);
      return;
    }
    setRemoteHits(
      (data.results || []).map((row) => ({
        ...row,
        doc_id: row.doc_id || row.source_uri || row.title,
        source: "weknora",
      })),
    );
  };

  const onImportRemote = async (knowledgeId: string) => {
    const kid = String(knowledgeId || "").trim();
    if (!kid) {
      toast.error("缺少远程文档 id");
      return;
    }
    setImportingId(kid);
    try {
      const data = await importWeknoraKnowledge({
        knowledge_id: kid,
        kb_id: wkKbId || undefined,
        workspace_id: workspaceId || undefined,
      });
      if (data.ok === false) {
        toast.error(String(data.error || "导入失败"));
      } else if (data.conflict) {
        toast.error("本地已有未同步修改，未覆盖");
      } else if (data.unchanged) {
        toast.success(`已存在本地 · ${data.doc_id || kid}`);
      } else {
        toast.success(`已导入本地 · ${data.title || data.doc_id || kid}`);
        setBrowseMode("local");
        setRemoteHits(null);
        if (data.doc_id) void onOpen(data.doc_id);
      }
      await refresh();
    } catch (err: any) {
      toast.error(String(err?.message || err || "导入失败"));
    } finally {
      setImportingId("");
    }
  };

  const onSearch = async () => {
    const q = query.trim();
    if (browseMode === "remote") {
      setLoading(true);
      try {
        await loadRemoteBrowse(q);
      } catch (err: any) {
        toast.error(String(err?.message || err));
      } finally {
        setLoading(false);
      }
      return;
    }
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
    if (selected.source === "weknora" || browseMode === "remote") return;
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

  const remoteMode = browseMode === "remote" && Boolean(wkKbId);
  const list: Array<KnowledgeHit & { content?: string }> = remoteMode
    ? ((remoteHits || []) as Array<KnowledgeHit & { content?: string }>)
    : hits ?? docs.map((d) => ({ ...d, score: undefined, snippet: undefined }));

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
                className="h-6 max-w-[160px] rounded border border-border bg-background px-1 text-[11px]"
                value={wkKbId || "__local__"}
                onChange={(e) =>
                  void onSelectWeknoraKb(
                    e.target.value === "__local__" ? "" : e.target.value,
                  )
                }
                title="绑定当前会话：本地或某一个 WeKnora 库"
              >
                <option value="__local__">本地知识库</option>
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
            {wkKbId ? (
              <div className="ml-auto flex rounded border border-border/70">
                <button
                  type="button"
                  className={cn(
                    "h-6 px-1.5 text-[10px]",
                    browseMode === "local"
                      ? "bg-background text-foreground"
                      : "text-muted-foreground",
                  )}
                  onClick={() => {
                    setBrowseMode("local");
                    setRemoteHits(null);
                  }}
                >
                  本地
                </button>
                <button
                  type="button"
                  className={cn(
                    "h-6 px-1.5 text-[10px]",
                    browseMode === "remote"
                      ? "bg-background text-foreground"
                      : "text-muted-foreground",
                  )}
                  onClick={() => {
                    setBrowseMode("remote");
                    setHits(null);
                    void loadRemoteBrowse(query.trim());
                  }}
                >
                  远程
                </button>
              </div>
            ) : null}
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
          placeholder={
            remoteMode ? "搜索远程 KB…（空则列出）" : "搜索知识库…"
          }
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
        {hits || remoteHits ? (
          <Button
            type="button"
            size="sm"
            variant="ghost"
            className="h-8 px-2 text-[11px]"
            onClick={() => {
              setHits(null);
              setRemoteHits(null);
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
            {remoteMode
              ? "远程 KB 暂无结果。输入关键词搜索，或清空后列出该库。"
              : "暂无文档。粘贴 Markdown、填路径导入，或点「同步文档」索引工作区。"}
          </p>
        ) : null}
        {list.map((row) => {
          const id = row.doc_id || row.source_uri || row.title || "remote";
          const isRemote = remoteMode || row.source === "weknora";
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
                  onClick={() => {
                    if (isRemote) {
                      setSelected({
                        doc_id: String(id),
                        title: row.title || String(id),
                        content: row.content || row.snippet || "",
                        source: "weknora",
                        source_uri: row.source_uri || String(id),
                        content_len: (row.content || row.snippet || "").length,
                      });
                      setEditTitle(row.title || "");
                      return;
                    }
                    void onOpen(String(id));
                  }}
                >
                  <div className="truncate font-medium text-foreground">
                    {row.title || id}
                    {isRemote ? (
                      <span className="ml-1 font-normal text-muted-foreground">
                        · 远程
                      </span>
                    ) : null}
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
                {isRemote ? (
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    className="h-7 shrink-0 px-1.5 text-[10px] text-muted-foreground hover:text-foreground"
                    title="导入到本地知识库"
                    disabled={Boolean(importingId)}
                    onClick={() => void onImportRemote(String(id))}
                  >
                    {importingId === String(id) ? "导入中…" : "导入到本地"}
                  </Button>
                ) : (
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    className="h-7 w-7 shrink-0 p-0 text-muted-foreground hover:text-destructive"
                    title="删除"
                    onClick={() => void onDelete(String(id))}
                  >
                    <Trash2 className="size-3.5" />
                  </Button>
                )}
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
              disabled={selected.source === "weknora" || browseMode === "remote"}
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
            {selected.source === "weknora" || browseMode === "remote" ? (
              <Button
                type="button"
                size="sm"
                variant="outline"
                className="h-7 shrink-0 px-1.5 text-[10px]"
                disabled={Boolean(importingId)}
                onClick={() => void onImportRemote(String(selected.doc_id))}
              >
                {importingId === selected.doc_id ? "导入中…" : "导入到本地"}
              </Button>
            ) : null}
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
