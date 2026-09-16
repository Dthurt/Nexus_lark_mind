import { useCallback, useEffect, useState } from "react";
import { BookOpen, Plus, RefreshCw, Search, Trash2 } from "lucide-react";
import { toast } from "sonner";

import {
  addKnowledgeDoc,
  deleteKnowledgeDoc,
  getKnowledgeDoc,
  listKnowledgeDocs,
  searchKnowledge,
  syncKnowledgeDocs,
  type KnowledgeDoc,
  type KnowledgeHit,
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
  const [query, setQuery] = useState("");
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [selected, setSelected] = useState<KnowledgeDoc | null>(null);
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [adding, setAdding] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listKnowledgeDocs({
        workspace_id: workspaceId || undefined,
        limit: 60,
      });
      setDocs(data.docs || []);
    } catch (err: any) {
      toast.error(String(err?.message || err || "加载失败"));
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

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
    if (!body) {
      toast.error("请粘贴 Markdown 内容");
      return;
    }
    setAdding(true);
    try {
      await addKnowledgeDoc({
        title: title.trim() || "笔记",
        content: body,
        tags: "manual",
        workspace_id: workspaceId || undefined,
        cwd: cwd || undefined,
      });
      setTitle("");
      setContent("");
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
    try {
      await deleteKnowledgeDoc(docId);
      if (selected?.doc_id === docId) setSelected(null);
      toast.success("已删除");
      await refresh();
    } catch (err: any) {
      toast.error(String(err?.message || err));
    }
  };

  const onOpen = async (docId: string) => {
    try {
      const doc = await getKnowledgeDoc(docId);
      setSelected(doc);
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
      await refresh();
    } catch (err: any) {
      toast.error(String(err?.message || err));
    } finally {
      setSyncing(false);
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
            本地 SQLite · 搜索后读取全文。可粘贴 Markdown 或同步{" "}
            <code className="text-[10px]">docs/**/*.md</code>
          </p>
        </div>
        <div className="flex shrink-0 gap-1">
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="h-7 px-2"
            disabled={syncing || !cwd}
            onClick={() => void onSync()}
            title={cwd ? "扫描工作区 Markdown" : "需要工作区"}
          >
            <RefreshCw className={cn("mr-1 size-3", syncing && "animate-spin")} />
            同步文档
          </Button>
        </div>
      </div>

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
            暂无文档。粘贴 Markdown 添加，或点「同步文档」索引工作区。
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
                  </div>
                  <div className="truncate font-mono text-[10px] text-muted-foreground">
                    {id}
                    {row.score != null ? ` · score ${row.score}` : ""}
                    {row.source ? ` · ${row.source}` : ""}
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
        <div className="max-h-[28%] min-h-0 overflow-auto rounded-md border border-border/50 bg-background/40 px-2 py-1.5">
          <div className="mb-1 text-[10px] uppercase tracking-wider text-muted-foreground">
            {selected.title} · {selected.content_len ?? selected.content?.length ?? 0} chars
          </div>
          <pre className="m-0 whitespace-pre-wrap font-mono text-[10.5px] leading-relaxed text-foreground/90">
            {(selected.content || "").slice(0, 6000)}
            {(selected.content || "").length > 6000 ? "\n…" : ""}
          </pre>
        </div>
      ) : null}

      <div className="shrink-0 space-y-1.5 border-t border-border/60 pt-2">
        <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
          粘贴添加
        </div>
        <Input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="标题（可选）"
          className="h-8 text-[12px]"
        />
        <textarea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          placeholder="粘贴 Markdown…"
          rows={4}
          className="w-full resize-y rounded-md border border-input bg-background px-2 py-1.5 font-mono text-[11px] outline-none focus-visible:ring-1 focus-visible:ring-ring"
        />
        <Button
          type="button"
          size="sm"
          className="h-8 w-full"
          disabled={adding || !content.trim()}
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
