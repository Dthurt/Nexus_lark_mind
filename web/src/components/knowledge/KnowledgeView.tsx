import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  BookOpen,
  Cloud,
  FilePlus2,
  FileSpreadsheet,
  FileText,
  FileUp,
  FolderUp,
  Layers3,
  Link2,
  MessageSquare,
  Plus,
  Presentation,
  RefreshCw,
  Search,
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
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  DEFAULT_LOCAL_KB_ID,
  isLocalKbId,
  kbScopeLabel,
  LOCAL_KB_ID,
} from "@/lib/knowledgeScope";
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

type BrowseRow = KnowledgeHit & { content?: string; kb_id?: string; tags?: string };
type IngestMode = "files" | "folder" | "url" | "paste" | "sync";
type SideTab = "ingest" | "preview";
type FileKindId = "all" | "pdf" | "word" | "ppt" | "excel" | "md" | "html";

const FILE_KINDS: {
  id: FileKindId;
  label: string;
  accept: string;
  hint: string;
}[] = [
  { id: "all", label: "全部", accept: ".pdf,.docx,.xlsx,.pptx,.md,.markdown,.mdx,.txt,.rst,.org,.html,.htm,.png,.jpg,.jpeg,.webp,.gif,.bmp", hint: "按后缀抽文本入库" },
  { id: "pdf", label: "PDF", accept: ".pdf", hint: "文字版直接抽；扫描件走 OCR" },
  { id: "word", label: "Word", accept: ".docx", hint: "仅 .docx，不含旧版 .doc" },
  { id: "ppt", label: "PPT", accept: ".pptx", hint: "仅 .pptx，不含旧版 .ppt" },
  { id: "excel", label: "Excel", accept: ".xlsx", hint: "仅 .xlsx" },
  { id: "md", label: "Markdown", accept: ".md,.markdown,.mdx,.txt,.rst,.org", hint: "含 txt / rst" },
  { id: "html", label: "HTML", accept: ".html,.htm", hint: "去标签后入库" },
];

const ACCEPT_ALL = FILE_KINDS[0].accept;
const SUPPORTED_EXT = new Set(
  ACCEPT_ALL.split(",").map((s) => s.trim().toLowerCase()),
);

const INGEST_TABS: { id: IngestMode; label: string; testId: string }[] = [
  { id: "files", label: "文件", testId: "knowledge-ingest-files" },
  { id: "folder", label: "文件夹", testId: "knowledge-ingest-folder" },
  { id: "url", label: "网页", testId: "knowledge-ingest-url" },
  { id: "paste", label: "粘贴", testId: "knowledge-ingest-paste" },
  { id: "sync", label: "工作区", testId: "knowledge-ingest-sync" },
];

function suffixOf(name: string): string {
  const i = name.lastIndexOf(".");
  return i >= 0 ? name.slice(i).toLowerCase() : "";
}

function inferEntryKind(row: BrowseRow): { id: string; label: string } {
  const src = `${row.source || ""} ${row.source_uri || ""} ${row.title || ""}`.toLowerCase();
  if (row.source === "weknora") return { id: "weknora", label: "WeKnora" };
  if ((row.source || "").startsWith("url:")) return { id: "url", label: "网页" };
  if (src.includes(".pdf")) return { id: "pdf", label: "PDF" };
  if (src.includes(".docx")) return { id: "word", label: "Word" };
  if (src.includes(".pptx")) return { id: "ppt", label: "PPT" };
  if (src.includes(".xlsx")) return { id: "excel", label: "Excel" };
  if (/\.(md|markdown|mdx)(\b|$)/.test(src)) return { id: "md", label: "Markdown" };
  if (/\.(html|htm)(\b|$)/.test(src)) return { id: "html", label: "HTML" };
  if ((row.source || "").startsWith("file:")) return { id: "workspace", label: "工作区" };
  if ((row.tags || "").includes("manual") && !(row.source || "").startsWith("upload:")) {
    return { id: "paste", label: "粘贴" };
  }
  if ((row.source || "").startsWith("upload:")) return { id: "file", label: "文件" };
  return { id: "doc", label: "文档" };
}

function jobTone(status?: string) {
  if (status === "completed") return "ok";
  if (status === "failed") return "bad";
  if (status === "processing") return "run";
  return "wait";
}

function partitionFiles(files: File[], accept: string): { ok: File[]; bad: File[] } {
  const allow = new Set(
    accept
      .split(",")
      .map((s) => s.trim().toLowerCase())
      .filter(Boolean),
  );
  const ok: File[] = [];
  const bad: File[] = [];
  for (const file of files) {
    const ext = suffixOf(file.name);
    if (allow.has(ext) && SUPPORTED_EXT.has(ext)) ok.push(file);
    else bad.push(file);
  }
  return { ok, bad };
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
  const [ingestMode, setIngestMode] = useState<IngestMode>("files");
  const [sideTab, setSideTab] = useState<SideTab>("ingest");
  const [fileKind, setFileKind] = useState<FileKindId>("all");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);

  const label = kbScopeLabel(boundKbId, boundKbName);
  const fileKindMeta = FILE_KINDS.find((k) => k.id === fileKind) || FILE_KINDS[0];
  const hybridLabel = stats?.embeddings_configured
    ? stats.hybrid_ready
      ? "hybrid 已就绪"
      : "hybrid 待命"
    : "关键词检索";
  const defaultLocal = localKbs.find((kb) => kb.id === DEFAULT_LOCAL_KB_ID);
  const extraLocal = localKbs.filter((kb) => kb.id && kb.id !== DEFAULT_LOCAL_KB_ID);
  const localActive = !boundKbId || boundKbId === DEFAULT_LOCAL_KB_ID;
  const remoteReady = Boolean(health?.configured && !health?.skipped);

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
    setRows([]);
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
    setSideTab(remote ? "preview" : "ingest");
  }, [loadList, loadJobs, remote]);

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

  const prevActiveJobs = useRef(0);
  useEffect(() => {
    if (prevActiveJobs.current > 0 && activeJobs.length === 0) {
      onCatalogRefresh?.();
    }
    prevActiveJobs.current = activeJobs.length;
  }, [activeJobs.length, onCatalogRefresh]);

  const enqueueFiles = async (fileList: FileList | File[] | null | undefined) => {
    const incoming = Array.from(fileList || []).filter(Boolean);
    if (!incoming.length) return;
    const { ok, bad } = partitionFiles(incoming, fileKindMeta.accept);
    if (bad.length) {
      toast.error(
        `未导入 ${bad.length} 个不支持的文件。当前入口支持 ${fileKindMeta.label}（${fileKindMeta.accept}）`,
      );
    }
    if (!ok.length) return;
    setUploading(true);
    try {
      const data = await ingestKnowledgeFiles(ok, {
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
        setSideTab("preview");
        return;
      }
      const doc = await getKnowledgeDoc(id, true);
      setSelected(doc);
      setChunks((doc.chunks || []).filter((c) => (c.chunk_type || "text") !== "parent"));
      setEditingChunk("");
      setSideTab("preview");
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
      onCatalogRefresh?.();
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
      onCatalogRefresh?.();
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

  const ingestCopy = {
    files: {
      title: `导入${fileKind === "all" ? "文件" : fileKindMeta.label}`,
      body: fileKindMeta.hint,
    },
    folder: {
      title: "导入文件夹",
      body: "按文件后缀分别解析；不支持的类型会跳过。",
    },
    url: {
      title: "抓取网页 / PDF 链接",
      body: "仅 http(s) 公网地址，内网与 localhost 会被拒绝。",
    },
    paste: {
      title: "粘贴 Markdown",
      body: "直接写入当前本地库，适合短说明和摘录。",
    },
    sync: {
      title: "同步工作区文档",
      body: "扫描已绑定文件夹里的 md / pdf / office。",
    },
  }[ingestMode];

  return (
    <div
      className={cn("nlm-knowledge-browse flex min-h-0 flex-1 flex-col bg-card/30", className)}
      data-testid="knowledge-page"
    >
      <header className="nlm-knowledge-hero shrink-0 border-b border-border px-3 py-2.5">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-1.5 text-[14px] font-semibold tracking-tight">
              <BookOpen className="size-4 text-teal" />
              知识库
            </div>
            <p className="m-0 mt-0.5 text-[12px] text-foreground/80">
              {remote ? "远程 WeKnora" : "本机 SQLite"} · 「{label}」
            </p>
            <div className="mt-1.5 flex flex-wrap gap-1">
              <span className="nlm-knowledge-pill">{hybridLabel}</span>
              {stats ? (
                <>
                  <span className="nlm-knowledge-pill">{stats.docs} 篇</span>
                  <span className="nlm-knowledge-pill">{stats.chunks} 块</span>
                </>
              ) : null}
              {activeJobs.length ? (
                <span className="nlm-knowledge-pill nlm-knowledge-pill--live">
                  {activeJobs.length} 个任务
                </span>
              ) : null}
            </div>
          </div>
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
        </div>
      </header>

      <div className="nlm-knowledge-shell min-h-0 flex-1">
        <aside className="nlm-knowledge-rail" data-testid="knowledge-library-rail">
          <div className="nlm-knowledge-rail-label">本机 SQLite</div>
          <button
            type="button"
            className={cn("nlm-knowledge-rail-item", localActive && "is-active")}
            data-testid="knowledge-scope-local"
            onClick={() => onBindKb?.(LOCAL_KB_ID, defaultLocal?.name || "本地知识库")}
          >
            <span className="min-w-0 flex-1 truncate">{defaultLocal?.name || "默认知识库"}</span>
            <span className="text-[10px] text-muted-foreground">{defaultLocal?.doc_count ?? 0}</span>
          </button>
          {extraLocal.map((kb) => (
            <button
              key={kb.id}
              type="button"
              className={cn("nlm-knowledge-rail-item", boundKbId === kb.id && "is-active")}
              data-testid={`knowledge-rail-kb-${kb.id}`}
              onClick={() => onBindKb?.(kb.id, kb.name || kb.id)}
            >
              <span className="min-w-0 flex-1 truncate">{kb.name || kb.id}</span>
              <span className="text-[10px] text-muted-foreground">{kb.doc_count ?? 0}</span>
            </button>
          ))}
          <div className="mt-1.5 space-y-1">
            <Input
              value={newKbName}
              onChange={(e) => setNewKbName(e.target.value)}
              placeholder="新库名称"
              className="h-7 text-[11px]"
              data-testid="knowledge-create-kb-name"
              onKeyDown={(e) => {
                if (e.key === "Enter") void onCreateKb();
              }}
            />
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="h-7 w-full px-2 text-[11px]"
              data-testid="knowledge-create-kb"
              disabled={creatingKb}
              onClick={() => void onCreateKb()}
            >
              <Plus className="mr-1 size-3" />
              新建本地库
            </Button>
          </div>

          <div className="nlm-knowledge-rail-label mt-3">WeKnora</div>
          {remoteReady ? (
            kbs.length ? (
              kbs.map((kb) => (
                <button
                  key={kb.id}
                  type="button"
                  className={cn("nlm-knowledge-rail-item", boundKbId === kb.id && "is-active")}
                  onClick={() => onBindKb?.(kb.id, kb.name || kb.id)}
                >
                  <Cloud className="size-3 shrink-0 opacity-70" />
                  <span className="min-w-0 flex-1 truncate">{kb.name || kb.id}</span>
                  {kb.doc_count != null ? (
                    <span className="text-[10px] text-muted-foreground">{kb.doc_count}</span>
                  ) : null}
                </button>
              ))
            ) : (
              <p className="m-0 px-1 text-[11px] text-muted-foreground">
                {health?.error || "暂无远程库"}
              </p>
            )
          ) : (
            <p className="m-0 px-1 text-[11px] leading-relaxed text-muted-foreground">
              未配置远程库。文档都写进左侧本机库。
            </p>
          )}
        </aside>

        <section className="nlm-knowledge-docs min-h-0">
          <div className="flex shrink-0 gap-1 border-b border-border px-2 py-2">
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={`在「${label}」中搜索…`}
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
          <div className="min-h-0 flex-1 space-y-1 overflow-y-auto overscroll-contain px-2 py-2">
            {loading && !rows.length ? (
              <p className="m-0 px-1 text-[12px] text-muted-foreground">加载中…</p>
            ) : null}
            {!loading && !rows.length ? (
              <div className="rounded-xl border border-dashed border-border/80 bg-muted/20 px-3 py-5 text-center text-[12px] text-muted-foreground">
                {remote
                  ? searched
                    ? "该远程库没有匹配结果。"
                    : "远程库暂无文档。换一个库，或到右侧导入到本机。"
                  : searched
                    ? "当前本地库没有匹配结果。"
                    : "从右侧选择一种导入方式：PDF / Word / PPT / Markdown 或网页、粘贴。"}
              </div>
            ) : null}
            {rows.map((row) => {
              const id = String(row.doc_id || row.source_uri || row.title || "row");
              const isRemote = remote || row.source === "weknora";
              const kind = inferEntryKind(row);
              return (
                <div
                  key={id + (row.chunk_id || "")}
                  className={cn("nlm-knowledge-card", selected?.doc_id === id && "is-active")}
                >
                  <div className="flex items-start justify-between gap-2">
                    <button type="button" className="min-w-0 flex-1 text-left" onClick={() => void onOpen(row)}>
                      <div className="flex items-center gap-1.5">
                        <span className={cn("nlm-knowledge-kind", `is-${kind.id}`)}>{kind.label}</span>
                        <span className="truncate text-[12px] font-medium">{row.title || id}</span>
                      </div>
                      <div className="mt-0.5 truncate font-mono text-[10px] text-muted-foreground">
                        {row.citation || row.source_uri || row.source || id}
                      </div>
                      {row.snippet ? (
                        <p className="m-0 mt-1 line-clamp-2 text-[11px] text-muted-foreground">{row.snippet}</p>
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
        </section>

        <aside className="nlm-knowledge-side min-h-0">
          {!remote ? (
            <div className="flex shrink-0 gap-1 border-b border-border p-1.5">
              <button
                type="button"
                className={cn("nlm-knowledge-side-tab", sideTab === "ingest" && "is-active")}
                data-testid="knowledge-side-ingest"
                onClick={() => setSideTab("ingest")}
              >
                导入
              </button>
              <button
                type="button"
                className={cn("nlm-knowledge-side-tab", sideTab === "preview" && "is-active")}
                data-testid="knowledge-side-preview"
                disabled={!selected}
                onClick={() => selected && setSideTab("preview")}
              >
                预览
              </button>
            </div>
          ) : null}

          {(remote || sideTab === "preview") && selected ? (
            <div className="min-h-0 flex-1 overflow-auto px-3 py-2">
              <div className="mb-1 flex items-center justify-between gap-2">
                <div className="min-w-0 truncate text-[12px] font-medium">{selected.title}</div>
                <button
                  type="button"
                  className="shrink-0 text-[10px] text-muted-foreground hover:text-foreground"
                  onClick={() => {
                    setSelected(null);
                    setChunks([]);
                    if (!remote) setSideTab("ingest");
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
                            <Textarea
                              value={chunkDraft}
                              onChange={(e) => setChunkDraft(e.target.value)}
                              rows={5}
                              className="font-mono text-[11px]"
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
            </div>
          ) : null}

          {!remote && sideTab === "ingest" ? (
            <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
              <div className="nlm-knowledge-ingest-modes" role="tablist" aria-label="导入方式">
                {INGEST_TABS.map((tab) => (
                  <button
                    key={tab.id}
                    type="button"
                    role="tab"
                    aria-selected={ingestMode === tab.id}
                    data-testid={tab.testId}
                    className={cn("nlm-knowledge-ingest-tab", ingestMode === tab.id && "is-active")}
                    onClick={() => setIngestMode(tab.id)}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>

              <div className="min-h-0 flex-1 space-y-2 overflow-auto px-3 py-2">
                <div>
                  <div className="text-[12px] font-medium">{ingestCopy.title}</div>
                  <p className="m-0 mt-0.5 text-[11px] text-muted-foreground">{ingestCopy.body}</p>
                </div>

                {ingestMode === "files" || ingestMode === "folder" ? (
                  <>
                    <div className="flex flex-wrap gap-1">
                      {FILE_KINDS.map((kind) => (
                        <button
                          key={kind.id}
                          type="button"
                          className={cn("nlm-knowledge-format", fileKind === kind.id && "is-on")}
                          data-testid={`knowledge-format-${kind.id}`}
                          onClick={() => setFileKind(kind.id)}
                        >
                          {kind.id === "pdf" ? <FileText className="size-3" /> : null}
                          {kind.id === "word" ? <FileText className="size-3" /> : null}
                          {kind.id === "ppt" ? <Presentation className="size-3" /> : null}
                          {kind.id === "excel" ? <FileSpreadsheet className="size-3" /> : null}
                          {kind.label}
                        </button>
                      ))}
                    </div>
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
                      {ingestMode === "folder" ? (
                        <FolderUp className="size-4 text-teal" />
                      ) : (
                        <FileUp className="size-4 text-teal" />
                      )}
                      <div className="min-w-0 text-[11px] text-muted-foreground">
                        {ingestMode === "folder"
                          ? "拖入文件夹，或点下方选择"
                          : `拖入 ${fileKindMeta.label}，或点下方选择`}
                      </div>
                    </div>
                    <input
                      ref={fileInputRef}
                      type="file"
                      multiple
                      className="hidden"
                      data-testid="knowledge-import-input"
                      accept={fileKindMeta.accept}
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
                    {ingestMode === "files" ? (
                      <Button
                        type="button"
                        size="sm"
                        className="h-8 w-full"
                        data-testid="knowledge-import-file"
                        disabled={uploading}
                        onClick={() => fileInputRef.current?.click()}
                      >
                        <FileUp className={cn("mr-1 size-3", uploading && "animate-pulse")} />
                        {uploading ? "导入中…" : `选择${fileKindMeta.label}`}
                      </Button>
                    ) : (
                      <Button
                        type="button"
                        size="sm"
                        className="h-8 w-full"
                        disabled={uploading}
                        onClick={() => folderInputRef.current?.click()}
                      >
                        <FolderUp className="mr-1 size-3" />
                        {uploading ? "导入中…" : "选择文件夹"}
                      </Button>
                    )}
                  </>
                ) : null}

                {ingestMode === "url" ? (
                  <div className="space-y-1.5">
                    <Input
                      value={title}
                      onChange={(e) => setTitle(e.target.value)}
                      placeholder="标题（可选）"
                      className="h-8 text-[12px]"
                    />
                    <Input
                      value={url}
                      onChange={(e) => setUrl(e.target.value)}
                      placeholder="https://…"
                      className="h-8 text-[12px]"
                      data-testid="knowledge-url-input"
                      onKeyDown={(e) => {
                        if (e.key === "Enter") void onUrlIngest();
                      }}
                    />
                    <Button
                      type="button"
                      size="sm"
                      className="h-8 w-full"
                      data-testid="knowledge-url-submit"
                      disabled={uploading || !url.trim()}
                      onClick={() => void onUrlIngest()}
                    >
                      <Link2 className="mr-1 size-3" />
                      抓取入库
                    </Button>
                  </div>
                ) : null}

                {ingestMode === "paste" ? (
                  <div className="space-y-1.5">
                    <Input
                      value={title}
                      onChange={(e) => setTitle(e.target.value)}
                      placeholder="标题（可选）"
                      className="h-8 text-[12px]"
                      data-testid="knowledge-add-title"
                    />
                    <Textarea
                      value={content}
                      onChange={(e) => setContent(e.target.value)}
                      placeholder="粘贴 Markdown…"
                      rows={6}
                      data-testid="knowledge-add-content"
                      className="font-mono text-[11px]"
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
                      写入当前库
                    </Button>
                  </div>
                ) : null}

                {ingestMode === "sync" ? (
                  <Button
                    type="button"
                    size="sm"
                    className="h-8 w-full"
                    disabled={syncing || !cwd}
                    onClick={() => void onSync()}
                  >
                    <RefreshCw className={cn("mr-1 size-3", syncing && "animate-spin")} />
                    {cwd ? "同步绑定文件夹" : "请先绑定工作区"}
                  </Button>
                ) : null}

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
              </div>
            </div>
          ) : null}

          {remote && !selected ? (
            <p className="m-0 px-3 py-3 text-[12px] text-muted-foreground">
              远程库只检索与预览。要把文档落到本机，点条目上的「导入本地」，或切回左侧本机库后再选导入方式。
            </p>
          ) : null}
        </aside>
      </div>
    </div>
  );
}

export default KnowledgeView;
