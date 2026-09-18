import { useCallback, useEffect, useState } from "react";
import { BookOpen, FilePlus2, RefreshCw, Search, Trash2 } from "lucide-react";
import { toast } from "sonner";

import {
  addKnowledgeDoc,
  deleteKnowledgeDoc,
  getKnowledgeDoc,
  getKnowledgeStats,
  getWeknoraKnowledge,
  importWeknoraKnowledge,
  listKnowledgeDocs,
  listWeknoraKnowledge,
  searchKnowledge,
  searchWeknora,
  syncKnowledgeDocs,
  type KnowledgeDoc,
  type KnowledgeHit,
  type KnowledgeStats,
  type WeknoraHealth,
  type WeknoraHit,
  type WeknoraKb,
} from "@/api/endpoints";
import { KnowledgeScopePicker } from "@/components/knowledge/KnowledgeScopePicker";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { kbScopeLabel } from "@/lib/knowledgeScope";
import { cn } from "@/lib/utils";

export type KnowledgeViewProps = {
  cwd?: string;
  workspaceId?: string;
  sessionId?: string;
  boundKbId?: string;
  boundKbName?: string;
  kbs?: WeknoraKb[];
  health?: WeknoraHealth | null;
  catalogLoading?: boolean;
  onBindKb?: (kbId: string, kbName: string) => void;
  onAskAbout?: (text: string) => void;
  className?: string;
};

type BrowseRow = KnowledgeHit & { content?: string; kb_id?: string };

export function KnowledgeView({
  cwd = "",
  workspaceId = "",
  boundKbId = "",
  boundKbName = "",
  kbs = [],
  health = null,
  catalogLoading = false,
  onBindKb,
  onAskAbout,
  className,
}: KnowledgeViewProps) {
  const remote = Boolean(boundKbId);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [stats, setStats] = useState<KnowledgeStats | null>(null);
  const [rows, setRows] = useState<BrowseRow[]>([]);
  const [selected, setSelected] = useState<KnowledgeDoc | null>(null);
  const [searched, setSearched] = useState(false);
  const [importingId, setImportingId] = useState("");
  const [adding, setAdding] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");

  const label = kbScopeLabel(boundKbId, boundKbName);

  const loadList = useCallback(async () => {
    setLoading(true);
    try {
      if (remote) {
        const data = await listWeknoraKnowledge({ kb_id: boundKbId, page_size: 40 });
        if (data.ok === false && data.error) {
          toast.error(String(data.error));
          setRows([]);
        } else {
          setRows(
            (data.items || []).map((row) => ({
              doc_id: String(row.id),
              title: row.title || row.id,
              snippet: (row.content || "").slice(0, 240),
              content: row.content,
              source_uri: row.id,
              source: "weknora",
              kb_id: boundKbId,
            })),
          );
        }
        setStats(null);
      } else {
        const [docs, st] = await Promise.all([
          listKnowledgeDocs({ workspace_id: workspaceId || undefined, limit: 60 }),
          getKnowledgeStats({ workspace_id: workspaceId || undefined }),
        ]);
        setRows((docs.docs || []).map((d) => ({ ...d })));
        setStats(st);
      }
      setSearched(false);
    } catch (err: any) {
      toast.error(String(err?.message || err || "加载失败"));
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, [boundKbId, remote, workspaceId]);

  useEffect(() => {
    void loadList();
    setSelected(null);
    setQuery("");
  }, [loadList]);

  const onSearch = async () => {
    const q = query.trim();
    if (!q) {
      await loadList();
      return;
    }
    setLoading(true);
    setSearched(true);
    try {
      if (remote) {
        const data = await searchWeknora({
          query: q,
          kb_id: boundKbId,
          weknora_kb_id: boundKbId,
          workspace_id: workspaceId || undefined,
          limit: 12,
        });
        if (data.ok === false && data.error) {
          toast.error(String(data.error));
          setRows([]);
        } else {
          setRows(
            (data.results || []).map((row: WeknoraHit) => ({
              doc_id: String(row.doc_id || row.source_uri || row.title || ""),
              title: row.title,
              snippet: row.snippet,
              source_uri: row.source_uri,
              score: row.score ?? undefined,
              citation: row.citation,
              source: "weknora",
              kb_id: row.kb_id || boundKbId,
            })),
          );
        }
      } else {
        const data = await searchKnowledge({
          query: q,
          workspace_id: workspaceId || undefined,
          limit: 12,
        });
        setRows(data.results || []);
      }
    } catch (err: any) {
      toast.error(String(err?.message || err));
    } finally {
      setLoading(false);
    }
  };

  const onOpen = async (row: BrowseRow) => {
    const id = String(row.doc_id || row.source_uri || "").trim();
    if (!id) return;
    try {
      if (remote || row.source === "weknora") {
        const full = await getWeknoraKnowledge(id);
        setSelected({
          doc_id: String(full.id || id),
          title: full.title || row.title || id,
          content: full.content || row.content || row.snippet || "",
          source: "weknora",
          source_uri: String(full.id || id),
          content_len: (full.content || row.content || "").length,
        });
        return;
      }
      const doc = await getKnowledgeDoc(id);
      setSelected(doc);
    } catch (err: any) {
      toast.error(String(err?.message || err));
    }
  };

  const onImport = async (knowledgeId: string) => {
    const kid = String(knowledgeId || "").trim();
    if (!kid) return;
    setImportingId(kid);
    try {
      const data = await importWeknoraKnowledge({
        knowledge_id: kid,
        kb_id: boundKbId || undefined,
        workspace_id: workspaceId || undefined,
      });
      if (data.ok === false) toast.error(String(data.error || "导入失败"));
      else if (data.conflict) toast.error("本地已有未同步修改，未覆盖");
      else toast.success(`已导入本地 · ${data.title || data.doc_id || kid}`);
    } catch (err: any) {
      toast.error(String(err?.message || err));
    } finally {
      setImportingId("");
    }
  };

  const onAddLocal = async () => {
    const body = content.trim();
    if (!body) {
      toast.error("请粘贴要写入的内容");
      return;
    }
    setAdding(true);
    try {
      await addKnowledgeDoc({
        title: title.trim() || undefined,
        content: body,
        tags: "manual",
        workspace_id: workspaceId || undefined,
        cwd: cwd || undefined,
      });
      setTitle("");
      setContent("");
      toast.success("已写入本地知识库");
      await loadList();
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
      await loadList();
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
      const data = await syncKnowledgeDocs({ cwd, workspace_id: workspaceId || undefined });
      toast.success(
        `同步完成 · 扫描 ${data.scanned ?? 0} · 新增 ${data.added ?? 0} · 更新 ${data.updated ?? 0}`,
      );
      await loadList();
    } catch (err: any) {
      toast.error(String(err?.message || err));
    } finally {
      setSyncing(false);
    }
  };

  return (
    <div className={cn("nlm-knowledge-browse flex min-h-0 flex-col bg-card/30", className)}>
      <header className="shrink-0 space-y-2 border-b border-border px-3 py-2.5">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-muted-foreground">
              <BookOpen className="size-3" />
              知识库
            </div>
            <p className="m-0 mt-0.5 text-[12px] text-foreground/90">
              检索并对话 · 当前「{label}」
            </p>
            <p className="m-0 mt-0.5 text-[11px] text-muted-foreground">
              {remote
                ? "右侧对话会基于该 WeKnora 库检索后作答"
                : stats
                  ? `${stats.docs} 篇 · ${stats.chunks} 块${stats.hybrid_ready ? " · hybrid" : ""}`
                  : "本地 SQLite，未选择远程库时的默认范围"}
            </p>
          </div>
          {!remote ? (
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="h-7 shrink-0 px-2"
              disabled={syncing || !cwd}
              onClick={() => void onSync()}
            >
              <RefreshCw className={cn("mr-1 size-3", syncing && "animate-spin")} />
              同步文档
            </Button>
          ) : null}
        </div>

        <KnowledgeScopePicker
          value={boundKbId}
          name={boundKbName}
          kbs={kbs}
          health={health}
          onChange={(id, kbName) => onBindKb?.(id, kbName)}
        />

        {health && health.configured && !health.skipped && !health.online ? (
          <p className="m-0 rounded-md border border-amber-500/30 bg-amber-500/10 px-2 py-1.5 text-[11px] text-amber-900 dark:text-amber-200">
            WeKnora 离线{health.error ? ` · ${health.error}` : ""}。可继续用本地知识库。
          </p>
        ) : null}

        <div className="flex gap-1">
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={remote ? `在「${label}」中搜索…` : "搜索本地知识库…"}
            className="h-8 text-[12px]"
            data-testid="knowledge-search-input"
            onKeyDown={(e) => {
              if (e.key === "Enter") void onSearch();
            }}
          />
          <Button
            type="button"
            size="sm"
            variant="secondary"
            className="h-8 px-2"
            data-testid="knowledge-search-submit"
            disabled={loading || catalogLoading}
            onClick={() => void onSearch()}
          >
            <Search className="size-3.5" />
          </Button>
        </div>
      </header>

      <div className="min-h-0 flex-1 space-y-1 overflow-y-auto overscroll-contain px-2 py-2">
        {loading && !rows.length ? (
          <p className="m-0 px-1 text-[12px] text-muted-foreground">加载中…</p>
        ) : null}
        {!loading && !rows.length ? (
          <div className="rounded-md border border-border/60 bg-muted/30 px-3 py-3 text-[12px] text-muted-foreground">
            {remote
              ? searched
                ? "该知识库没有匹配结果。"
                : "远程库暂无文档。输入关键词搜索，或清空后列出该库。"
              : searched
                ? "本地知识库没有匹配结果。"
                : "暂无文档。在下方粘贴 Markdown，或绑定工作区后同步 docs。"}
          </div>
        ) : null}
        {rows.map((row) => {
          const id = String(row.doc_id || row.source_uri || row.title || "row");
          const isRemote = remote || row.source === "weknora";
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
                  onClick={() => void onOpen(row)}
                >
                  <div className="truncate text-[12px] font-medium text-foreground">
                    {row.title || id}
                    {row.heading ? (
                      <span className="font-normal text-muted-foreground"> · {row.heading}</span>
                    ) : null}
                  </div>
                  <div className="truncate font-mono text-[10px] text-muted-foreground">
                    {row.citation || row.source_uri || row.source || id}
                    {row.score != null ? ` · score ${row.score}` : ""}
                  </div>
                  {row.snippet ? (
                    <p className="m-0 mt-1 line-clamp-3 text-[11px] text-muted-foreground">
                      {row.snippet}
                    </p>
                  ) : null}
                </button>
                <div className="flex shrink-0 flex-col gap-0.5">
                  {onAskAbout ? (
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      className="h-6 px-1.5 text-[10px] text-muted-foreground"
                      onClick={() =>
                        onAskAbout(`请根据知识库条目「${row.title || id}」说明要点，并引用原文。`)
                      }
                    >
                      提问
                    </Button>
                  ) : null}
                  {isRemote ? (
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      className="h-6 px-1.5 text-[10px] text-muted-foreground"
                      disabled={Boolean(importingId)}
                      onClick={() => void onImport(id)}
                    >
                      {importingId === id ? "导入中…" : "导入本地"}
                    </Button>
                  ) : (
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      className="h-6 w-6 p-0 text-muted-foreground hover:text-destructive"
                      title="删除"
                      onClick={() => void onDelete(id)}
                    >
                      <Trash2 className="size-3.5" />
                    </Button>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {selected ? (
        <div className="max-h-[34%] min-h-0 overflow-auto border-t border-border bg-background/50 px-3 py-2">
          <div className="mb-1 flex items-center justify-between gap-2">
            <div className="min-w-0 truncate text-[12px] font-medium">{selected.title}</div>
            <button
              type="button"
              className="shrink-0 text-[10px] text-muted-foreground hover:text-foreground"
              onClick={() => setSelected(null)}
            >
              关闭
            </button>
          </div>
          {selected.source_uri ? (
            <div className="mb-1 truncate font-mono text-[10px] text-muted-foreground">
              {selected.source_uri}
            </div>
          ) : null}
          <pre className="m-0 whitespace-pre-wrap font-mono text-[11px] leading-relaxed text-foreground/90">
            {(selected.content || "").slice(0, 8000)}
            {(selected.content || "").length > 8000 ? "\n…" : ""}
          </pre>
        </div>
      ) : null}

      {!remote ? (
        <div className="shrink-0 space-y-1.5 border-t border-border px-3 py-2">
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground">写入本地</div>
          <Input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="标题（可选）"
            className="h-8 text-[12px]"
            data-testid="knowledge-add-title"
          />
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            placeholder="粘贴 Markdown…"
            rows={2}
            data-testid="knowledge-add-content"
            className="w-full resize-y rounded-md border border-input bg-background px-2 py-1.5 font-mono text-[11px] outline-none focus-visible:ring-1 focus-visible:ring-ring"
          />
          <Button
            type="button"
            size="sm"
            className="h-8 w-full"
            data-testid="knowledge-add-submit"
            disabled={adding || !content.trim()}
            onClick={() => void onAddLocal()}
          >
            <FilePlus2 className="mr-1 size-3.5" />
            写入知识库
          </Button>
        </div>
      ) : null}

      <p className="m-0 shrink-0 border-t border-border px-3 py-1.5 text-[11px] text-muted-foreground">
        右侧输入即针对「{label}」提问，与主对话同一会话。
      </p>
    </div>
  );
}

export default KnowledgeView;
