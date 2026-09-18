import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  BookOpen,
  FilePlus2,
  FileUp,
  FolderUp,
  Globe,
  Layers3,
  Link2,
  MessageSquare,
  Plus,
  RefreshCw,
  Search,
  Sparkles,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";

import {
  addKnowledgeDoc,
  createLocalKnowledgeBase,
  deleteKnowledgeDoc,
  getKnowledgeDoc,
  getKnowledgeStats,
  getWeknoraKnowledge,
  importWeknoraKnowledge,
  ingestKnowledgeFiles,
  ingestKnowledgeUrl,
  listKnowledgeDocs,
  listKnowledgeJobs,
  listWeknoraKnowledge,
  patchKnowledgeChunk,
  searchKnowledge,
  searchWeknora,
  syncKnowledgeDocs,
  type KnowledgeChunk,
  type KnowledgeDoc,
  type KnowledgeHit,
  type KnowledgeIngestJob,
  type KnowledgeStats,
  type LocalKnowledgeBase,
  type WeknoraHealth,
  type WeknoraHit,
  type WeknoraKb,
} from "@/api/endpoints";
import { KnowledgeScopePicker } from "@/components/knowledge/KnowledgeScopePicker";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { DEFAULT_LOCAL_KB_ID, isLocalKbId, kbScopeLabel } from "@/lib/knowledgeScope";
import { cn } from "@/lib/utils";

export type KnowledgeViewProps = {
  cwd?: string;
  workspaceId?: string;
  sessionId?: string;
  boundKbId?: string;
  boundKbName?: string;
  kbs?: WeknoraKb[];
  localKbs?: LocalKnowledgeBase[];
  health?: WeknoraHealth | null;
  catalogLoading?: boolean;
  onBindKb?: (kbId: string, kbName: string) => void;
  onCatalogRefresh?: () => void;
  onAskAbout?: (text: string) => void;
  className?: string;
};

type BrowseRow = KnowledgeHit & { content?: string; kb_id?: string };

const ACCEPT =
  ".pdf,.docx,.xlsx,.pptx,.md,.markdown,.mdx,.txt,.rst,.org,.html,.htm,.png,.jpg,.jpeg,.webp,.gif,.bmp";

function jobTone(status?: string) {
  if (status === "completed") return "ok";
  if (status === "failed") return "bad";
  if (status === "processing") return "run";
  return "wait";
}

export function KnowledgeView({
  cwd = "",
  workspaceId = "",
  boundKbId = "",
  boundKbName = "",
  kbs = [],
  localKbs = [],
  health = null,
  catalogLoading = false,
  onBindKb,
  onCatalogRefresh,
  onAskAbout,
  className,
}: KnowledgeViewProps) {
  const remote = !isLocalKbId(boundKbId);
  const localKbId = remote ? "" : boundKbId || DEFAULT_LOCAL_KB_ID;
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [stats, setStats] = useState<KnowledgeStats | null>(null);
  const [rows, setRows] = useState<BrowseRow[]>([]);
  const [selected, setSelected] = useState<KnowledgeDoc | null>(null);
  const [chunks, setChunks] = useState<KnowledgeChunk[]>([]);
  const [editingChunk, setEditingChunk] = useState("");
  const [chunkDraft, setChunkDraft] = useState("");
  const [savingChunk, setSavingChunk] = useState(false);
  const [searched, setSearched] = useState(false);
  const [importingId, setImportingId] = useState("");
  const [adding, setAdding] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [creatingKb, setCreatingKb] = useState(false);
  const [newKbName, setNewKbName] = useState("");
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [url, setUrl] = useState("");
  const [jobs, setJobs] = useState<KnowledgeIngestJob[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);

  const label = kbScopeLabel(boundKbId, boundKbName);
  const hybridLabel = stats?.embeddings_configured
    ? stats.hybrid_ready
      ? "hybrid 已就绪"
      : "hybrid 待命"
    : "关键词检索";

  const activeJobs = useMemo(
    () => jobs.filter((j) => j.status === "pending" || j.status === "processing"),
    [jobs],
  );

  const loadJobs = useCallback(async () => {
    if (remote) return;
    try {
      const data = await listKnowledgeJobs({
        workspace_id: workspaceId || undefined,
        kb_id: localKbId,
        limit: 12,
      });
      setJobs(data.jobs || []);
    } catch {
      setJobs([]);
    }
  }, [localKbId, remote, workspaceId]);

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
          listKnowledgeDocs({
            workspace_id: workspaceId || undefined,
            kb_id: localKbId,
            limit: 60,
          }),
          getKnowledgeStats({ workspace_id: workspaceId || undefined, kb_id: localKbId }),
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
  }, [boundKbId, localKbId, remote, workspaceId]);

  useEffect(() => {
    void loadList();
    void loadJobs();
    setSelected(null);
    setChunks([]);
    setQuery("");
  }, [loadList, loadJobs]);

  useEffect(() => {
    if (!activeJobs.length) return;
    const timer = window.setInterval(() => {
      void (async () => {
        await loadJobs();
        await loadList();
      })();
    }, 1200);
    return () => window.clearInterval(timer);
  }, [activeJobs.length, loadJobs, loadList]);

  const enqueueFiles = async (fileList: FileList | File[] | null | undefined) => {
    const files = Array.from(fileList || []).filter(Boolean);
    if (!files.length) return;
    setUploading(true);
    try {
      const data = await ingestKnowledgeFiles(files, {
        workspaceId,
        kbId: localKbId,
      });
      const n = data.jobs?.length || 0;
      toast.success(n ? `已排队 ${n} 个导入任务` : "已提交导入");
      if (data.errors?.length) toast.error(data.errors.slice(0, 3).join("；"));
      await loadJobs();
    } catch (err: any) {
      toast.error(String(err?.message || err || "导入失败"));
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
      if (folderInputRef.current) folderInputRef.current.value = "";
    }
  };

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
          kb_id: localKbId,
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
        setChunks([]);
        return;
      }
      const doc = await getKnowledgeDoc(id, true);
      setSelected(doc);
      setChunks((doc.chunks || []).filter((c) => (c.chunk_type || "text") !== "parent"));
      setEditingChunk("");
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
        kb_id: localKbId,
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
      if (selected?.doc_id === docId) {
        setSelected(null);
        setChunks([]);
      }
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

  const onCreateKb = async () => {
    const name = newKbName.trim();
    if (!name) {
      toast.error("请输入知识库名称");
      return;
    }
    setCreatingKb(true);
    try {
      const row = await createLocalKnowledgeBase({
        name,
        workspace_id: workspaceId || undefined,
      });
      setNewKbName("");
      toast.success(`已创建「${row.name}」`);
      onCatalogRefresh?.();
      onBindKb?.(row.id, row.name);
    } catch (err: any) {
      toast.error(String(err?.message || err));
    } finally {
      setCreatingKb(false);
    }
  };

  const onUrlIngest = async () => {
    const target = url.trim();
    if (!target) {
      toast.error("请输入 http(s) 链接");
      return;
    }
    setUploading(true);
    try {
      await ingestKnowledgeUrl({
        url: target,
        workspace_id: workspaceId || undefined,
        kb_id: localKbId,
        title: title.trim() || undefined,
      });
      setUrl("");
      toast.success("链接已加入导入队列");
      await loadJobs();
    } catch (err: any) {
      toast.error(String(err?.message || err || "链接导入失败"));
    } finally {
      setUploading(false);
    }
  };

  const onSaveChunk = async () => {
    if (!editingChunk) return;
    setSavingChunk(true);
    try {
      const row = await patchKnowledgeChunk(editingChunk, { content: chunkDraft });
      setChunks((prev) => prev.map((c) => (c.chunk_id === editingChunk ? { ...c, ...row } : c)));
      setEditingChunk("");
      toast.success("分块已更新");
    } catch (err: any) {
      toast.error(String(err?.message || err));
    } finally {
      setSavingChunk(false);
    }
  };

  return (
    <div
      className={cn("nlm-knowledge-browse flex min-h-0 flex-1 flex-col bg-card/30", className)}
      data-testid="knowledge-page"
    >
      <header className="nlm-knowledge-hero shrink-0 space-y-3 border-b border-border px-4 py-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-1.5 text-[14px] font-semibold tracking-tight text-foreground">
              <BookOpen className="size-4 text-teal" />
              知识库
            </div>
            <p className="m-0 mt-1 text-[12px] text-foreground/85">
              当前「{label}」· 导入、分块与检索都在这一页完成
            </p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              <span className="nlm-knowledge-pill">{hybridLabel}</span>
              {stats ? (
                <>
                  <span className="nlm-knowledge-pill">{stats.docs} 篇</span>
                  <span className="nlm-knowledge-pill">{stats.chunks} 块</span>
                </>
              ) : remote ? (
                <span className="nlm-knowledge-pill">WeKnora</span>
              ) : null}
              {activeJobs.length ? (
                <span className="nlm-knowledge-pill nlm-knowledge-pill--live">
                  {activeJobs.length} 个任务进行中
                </span>
              ) : null}
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-1">
            {onAskAbout ? (
              <Button
                type="button"
                size="sm"
                variant="secondary"
                className="h-7 px-2"
                data-testid="knowledge-go-chat"
                onClick={() => onAskAbout("")}
              >
                <MessageSquare className="mr-1 size-3" />
                去对话
              </Button>
            ) : null}
            {!remote ? (
              <Button
                type="button"
                size="sm"
                variant="outline"
                className="h-7 px-2"
                disabled={syncing || !cwd}
                onClick={() => void onSync()}
              >
                <RefreshCw className={cn("mr-1 size-3", syncing && "animate-spin")} />
                同步文档
              </Button>
            ) : null}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <KnowledgeScopePicker
            value={boundKbId}
            name={boundKbName}
            kbs={kbs}
            localKbs={localKbs}
            health={health}
            onChange={(id, kbName) => onBindKb?.(id, kbName)}
          />
          {!remote ? (
            <div className="flex min-w-0 flex-1 items-center gap-1">
              <Input
                value={newKbName}
                onChange={(e) => setNewKbName(e.target.value)}
                placeholder="新建本地库名称"
                className="h-8 max-w-[180px] text-[12px]"
                data-testid="knowledge-create-kb-name"
                onKeyDown={(e) => {
                  if (e.key === "Enter") void onCreateKb();
                }}
              />
              <Button
                type="button"
                size="sm"
                variant="outline"
                className="h-8 px-2"
                data-testid="knowledge-create-kb"
                disabled={creatingKb}
                onClick={() => void onCreateKb()}
              >
                <Plus className="mr-1 size-3" />
                新建库
              </Button>
            </div>
          ) : null}
        </div>

        {health && health.configured && !health.skipped && !health.online ? (
          <p className="m-0 rounded-md border border-amber-500/30 bg-amber-500/10 px-2 py-1.5 text-[11px] text-amber-900 dark:text-amber-200">
            WeKnora 离线{health.error ? ` · ${health.error}` : ""}。可继续用本地知识库。
          </p>
        ) : null}

        <div className="flex gap-1">
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={remote ? `在「${label}」中搜索…` : "搜索标题、正文或分块…"}
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

      {!remote ? (
        <section className="shrink-0 space-y-2 border-b border-border px-4 py-3">
          <div
            className={cn("nlm-knowledge-drop", dragOver && "nlm-knowledge-drop--over")}
            data-testid="knowledge-dropzone"
            onDragOver={(e) => {
              e.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragOver(false);
              void enqueueFiles(e.dataTransfer.files);
            }}
          >
            <Sparkles className="size-4 text-teal" />
            <div className="min-w-0">
              <div className="text-[12px] font-medium">拖入文件或文件夹</div>
              <div className="text-[11px] text-muted-foreground">
                PDF / Office / Markdown / HTML · 扫描件自动尝试 OCR · 有模型 Key 时默认 hybrid 向量
              </div>
            </div>
            <div className="ml-auto flex flex-wrap gap-1">
              <input
                ref={fileInputRef}
                type="file"
                multiple
                className="hidden"
                data-testid="knowledge-import-input"
                accept={ACCEPT}
                onChange={(e) => void enqueueFiles(e.target.files)}
              />
              <input
                ref={folderInputRef}
                type="file"
                className="hidden"
                data-testid="knowledge-import-folder"
                // @ts-expect-error webkitdirectory is non-standard but supported
                webkitdirectory=""
                multiple
                onChange={(e) => void enqueueFiles(e.target.files)}
              />
              <Button
                type="button"
                size="sm"
                variant="outline"
                className="h-7 px-2"
                data-testid="knowledge-import-file"
                disabled={uploading}
                onClick={() => fileInputRef.current?.click()}
              >
                <FileUp className={cn("mr-1 size-3", uploading && "animate-pulse")} />
                {uploading ? "导入中…" : "多文件"}
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                className="h-7 px-2"
                disabled={uploading}
                onClick={() => folderInputRef.current?.click()}
              >
                <FolderUp className="mr-1 size-3" />
                文件夹
              </Button>
            </div>
          </div>
          <div className="flex gap-1">
            <div className="relative min-w-0 flex-1">
              <Globe className="pointer-events-none absolute left-2 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="粘贴网页或 PDF 链接…"
                className="h-8 pl-7 text-[12px]"
                data-testid="knowledge-url-input"
                onKeyDown={(e) => {
                  if (e.key === "Enter") void onUrlIngest();
                }}
              />
            </div>
            <Button
              type="button"
              size="sm"
              variant="secondary"
              className="h-8 px-2"
              data-testid="knowledge-url-submit"
              disabled={uploading || !url.trim()}
              onClick={() => void onUrlIngest()}
            >
              <Link2 className="mr-1 size-3" />
              抓取
            </Button>
          </div>
          {jobs.length ? (
            <div className="nlm-knowledge-jobs" data-testid="knowledge-jobs">
              {jobs.slice(0, 6).map((job) => (
                <div key={job.job_id} className={cn("nlm-knowledge-job", `is-${jobTone(job.status)}`)}>
                  <div className="min-w-0 flex-1 truncate">
                    <span className="font-medium">{job.filename || job.source_uri || job.job_id}</span>
                    <span className="text-muted-foreground">
                      {" "}
                      · {job.status}
                      {job.message ? ` · ${job.message}` : ""}
                    </span>
                  </div>
                  <div className="nlm-knowledge-job-bar">
                    <i style={{ width: `${Math.max(6, Number(job.progress || 0))}%` }} />
                  </div>
                  {job.error ? (
                    <div className="w-full truncate text-[10px] text-destructive">{job.error}</div>
                  ) : null}
                </div>
              ))}
            </div>
          ) : null}
        </section>
      ) : null}

      <div className="nlm-knowledge-split min-h-0 flex-1">
        <div className="min-h-0 space-y-1 overflow-y-auto overscroll-contain px-2 py-2">
          {loading && !rows.length ? (
            <p className="m-0 px-1 text-[12px] text-muted-foreground">加载中…</p>
          ) : null}
          {!loading && !rows.length ? (
            <div className="rounded-xl border border-dashed border-border/80 bg-muted/20 px-3 py-5 text-center text-[12px] text-muted-foreground">
              {remote
                ? searched
                  ? "该知识库没有匹配结果。"
                  : "远程库暂无文档。输入关键词搜索，或清空后列出该库。"
                : searched
                  ? "本地知识库没有匹配结果。"
                  : "把 PDF、文件夹或链接拖到上方。扫描件会走 OCR，有 Key 时自动写入向量。"}
            </div>
          ) : null}
          {rows.map((row) => {
            const id = String(row.doc_id || row.source_uri || row.title || "row");
            const isRemote = remote || row.source === "weknora";
            return (
              <div
                key={id + (row.chunk_id || "")}
                className={cn(
                  "nlm-knowledge-card",
                  selected?.doc_id === id && "is-active",
                )}
              >
                <div className="flex items-start justify-between gap-2">
                  <button type="button" className="min-w-0 flex-1 text-left" onClick={() => void onOpen(row)}>
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
        <aside className="nlm-knowledge-preview min-h-0 overflow-auto border-t border-border bg-background/40 px-3 py-2">
              <div className="mb-1 flex items-center justify-between gap-2">
                <div className="min-w-0 truncate text-[12px] font-medium">{selected.title}</div>
                <button
                  type="button"
                  className="shrink-0 text-[10px] text-muted-foreground hover:text-foreground"
                  onClick={() => {
                    setSelected(null);
                    setChunks([]);
                  }}
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
                {(selected.content || "").slice(0, 5000)}
                {(selected.content || "").length > 5000 ? "\n…" : ""}
              </pre>
              {!remote && chunks.length ? (
                <div className="mt-3 space-y-1.5" data-testid="knowledge-chunk-editor">
                  <div className="flex items-center gap-1 text-[10px] uppercase tracking-wider text-muted-foreground">
                    <Layers3 className="size-3" />
                    分块预览 / 编辑
                  </div>
                  {chunks.map((chunk) => {
                    const editing = editingChunk === chunk.chunk_id;
                    return (
                      <div key={chunk.chunk_id} className="rounded-md border border-border/60 bg-card/60 p-2">
                        <div className="mb-1 flex items-center justify-between gap-2 text-[10px] text-muted-foreground">
                          <span>
                            #{chunk.chunk_index}
                            {chunk.heading ? ` · ${chunk.heading}` : ""}
                            {chunk.has_embedding ? " · vec" : ""}
                          </span>
                          {!editing ? (
                            <button
                              type="button"
                              className="text-teal hover:underline"
                              onClick={() => {
                                setEditingChunk(chunk.chunk_id);
                                setChunkDraft(chunk.content || "");
                              }}
                            >
                              编辑
                            </button>
                          ) : null}
                        </div>
                        {editing ? (
                          <>
                            <textarea
                              value={chunkDraft}
                              onChange={(e) => setChunkDraft(e.target.value)}
                              rows={5}
                              className="w-full resize-y rounded-md border border-input bg-background px-2 py-1.5 font-mono text-[11px] outline-none focus-visible:ring-1 focus-visible:ring-ring"
                            />
                            <div className="mt-1 flex gap-1">
                              <Button
                                type="button"
                                size="sm"
                                className="h-7 px-2"
                                disabled={savingChunk}
                                onClick={() => void onSaveChunk()}
                              >
                                保存分块
                              </Button>
                              <Button
                                type="button"
                                size="sm"
                                variant="ghost"
                                className="h-7 px-2"
                                onClick={() => setEditingChunk("")}
                              >
                                取消
                              </Button>
                            </div>
                          </>
                        ) : (
                          <p className="m-0 line-clamp-4 whitespace-pre-wrap text-[11px] text-foreground/80">
                            {chunk.content}
                          </p>
                        )}
                      </div>
                    );
                  })}
                </div>
              ) : null}
        </aside>
        ) : null}
      </div>

      {!remote ? (
        <div className="shrink-0 space-y-1.5 border-t border-border px-3 py-2">
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
            写入本地 · PDF / Word / Excel / PPT / Markdown / HTML
          </div>
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
        针对「{label}」提问请回到对话页；主输入框已绑定该库。
      </p>
    </div>
  );
}

export default KnowledgeView;
