import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, BookOpen, Clock3, History, Pencil, Save, Search, Sparkles } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { toast } from "sonner";

import {
  distillWiki,
  getWikiPage,
  listKnowledgeJobs,
  listWikiPages,
  putWikiPage,
  rollbackWikiPage,
  type WikiPage,
  type WikiRevision,
} from "@/api/endpoints";
import { MarkdownBody } from "@/components/chat/MarkdownBody";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { usePrefersReducedMotion } from "@/lib/motion";
import { parseKnowledgeCiteHref } from "@/lib/kbCite";
import { rewriteWikiLinks } from "@/lib/wikiLinks";
import { cn } from "@/lib/utils";

export type WikiLayerProps = {
  kbId: string;
  slug?: string;
  workspaceId?: string;
  remote?: boolean;
  onOpenSlug: (slug?: string) => void;
  onAskAbout?: (text: string) => void;
};

function formatRel(iso?: string | null) {
  if (!iso) return "";
  const raw = iso.trim();
  const normalized = /Z$|[+-]\d{2}:\d{2}$/.test(raw) ? raw : `${raw}Z`;
  const t = Date.parse(normalized);
  if (!Number.isFinite(t)) return "";
  const delta = Date.now() - t;
  if (delta < 45_000) return "刚刚";
  if (delta < 3600_000) return `${Math.max(1, Math.floor(delta / 60_000))} 分钟前`;
  if (delta < 86400_000) return `${Math.floor(delta / 3600_000)} 小时前`;
  if (delta < 6.5 * 86400_000) return `${Math.floor(delta / 86400_000)} 天前`;
  return new Date(t).toLocaleDateString();
}

export function WikiLayer({
  kbId,
  slug = "",
  workspaceId = "",
  remote = false,
  onOpenSlug,
  onAskAbout,
}: WikiLayerProps) {
  const reduced = usePrefersReducedMotion();
  const [pages, setPages] = useState<WikiPage[]>([]);
  const [page, setPage] = useState<WikiPage | null>(null);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState("");
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [saving, setSaving] = useState(false);
  const [distilling, setDistilling] = useState(false);
  const [pendingRev, setPendingRev] = useState<WikiRevision | null>(null);

  const dirty = Boolean(page && (title !== (page.title || "") || content !== (page.content || "")));

  const loadList = async () => {
    if (remote || !kbId) {
      setPages([]);
      return;
    }
    setLoading(true);
    try {
      const data = await listWikiPages({ kb_id: kbId, limit: 200 });
      setPages(data.pages || []);
    } catch (err: any) {
      toast.error(String(err?.message || err || "加载 Wiki 失败"));
    } finally {
      setLoading(false);
    }
  };

  const loadPage = async (nextSlug: string) => {
    if (remote || !kbId || !nextSlug) {
      setPage(null);
      return;
    }
    setLoading(true);
    try {
      const row = await getWikiPage(nextSlug, kbId);
      setPage(row);
      setTitle(row.title || "");
      setContent(row.content || "");
      setEditing(false);
    } catch (err: any) {
      setPage(null);
      toast.error(String(err?.message || err || "Wiki 页不存在"));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadList();
  }, [kbId, remote]);

  useEffect(() => {
    if (slug) void loadPage(slug);
    else {
      setPage(null);
      setEditing(false);
    }
  }, [kbId, slug, remote]);

  const rendered = useMemo(
    () => rewriteWikiLinks(page?.content || "", kbId),
    [page?.content, kbId],
  );

  const visiblePages = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return pages;
    return pages.filter((item) =>
      `${item.title} ${item.slug}`.toLowerCase().includes(q),
    );
  }, [pages, filter]);

  const onSave = async () => {
    if (!slug) return;
    setSaving(true);
    try {
      const row = await putWikiPage(slug, {
        kb_id: kbId,
        title,
        content,
        message: "edit",
        workspace_id: workspaceId || undefined,
      });
      setPage(row);
      setTitle(row.title || "");
      setContent(row.content || "");
      setEditing(false);
      toast.success("已保存");
      void loadList();
    } catch (err: any) {
      toast.error(String(err?.message || err || "保存失败"));
    } finally {
      setSaving(false);
    }
  };

  const onRollback = async (revisionId: string) => {
    if (!slug) return;
    setSaving(true);
    try {
      const row = await rollbackWikiPage(slug, { kb_id: kbId, revision_id: revisionId });
      setPage(row);
      setTitle(row.title || "");
      setContent(row.content || "");
      setEditing(false);
      toast.success("已回滚");
      void loadList();
    } catch (err: any) {
      toast.error(String(err?.message || err || "回滚失败"));
    } finally {
      setSaving(false);
      setPendingRev(null);
    }
  };

  const onDistill = async () => {
    setDistilling(true);
    try {
      const data = await distillWiki({
        kb_id: kbId,
        workspace_id: workspaceId || undefined,
      });
      toast.success(data.job?.message || "正在生成本库 Wiki");
      const jobId = data.job?.job_id;
      for (let i = 0; i < 16; i += 1) {
        await new Promise((resolve) => window.setTimeout(resolve, 700));
        void loadList();
        if (!jobId) break;
        const jobs = await listKnowledgeJobs({ kb_id: kbId, limit: 12 });
        const hit = (jobs.jobs || []).find((job) => job.job_id === jobId);
        if (!hit || hit.status === "completed" || hit.status === "failed") {
          if (hit?.status === "failed") toast.error(hit.error || "蒸馏失败");
          break;
        }
      }
    } catch (err: any) {
      toast.error(String(err?.message || err || "蒸馏失败"));
    } finally {
      setDistilling(false);
      void loadList();
    }
  };

  useEffect(() => {
    if (!editing) return;
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "s") {
        e.preventDefault();
        if (dirty) void onSave();
      }
      if (e.key === "Escape" && !dirty) setEditing(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [editing, dirty, slug, title, content]);

  if (remote) {
    return (
      <div className="nlm-wiki-pane" data-testid="knowledge-wiki-page">
        <div className="nlm-kb-empty">
          <div className="nlm-kb-empty-mark">Wiki</div>
          <p className="nlm-kb-empty-title">远程库没有第二层 Wiki</p>
          <p className="nlm-kb-empty-copy">先把 WeKnora 文档导入左侧本机库，再蒸馏。</p>
        </div>
      </div>
    );
  }

  if (slug && page) {
    return (
      <div className="nlm-wiki-pane" data-testid="knowledge-wiki-page">
        <div className="nlm-wiki-toolbar">
          <button type="button" className="nlm-kb-ghost" onClick={() => onOpenSlug()}>
            <ArrowLeft className="size-3.5" />
            目录
          </button>
          <div className="nlm-wiki-crumb min-w-0 flex-1">
            <span className="truncate">{page.title}</span>
            {page.status === "draft" ? <span className="nlm-knowledge-pill">待合并</span> : null}
            {dirty ? <span className="nlm-knowledge-pill nlm-knowledge-pill--live">未保存</span> : null}
          </div>
          {onAskAbout ? (
            <Button
              type="button"
              size="sm"
              variant="ghost"
              className="h-7 px-2"
              onClick={() => onAskAbout(`请根据 Wiki「${page.title}」说明要点，并引用 wiki:${page.slug}。`)}
            >
              提问
            </Button>
          ) : null}
          <Button
            type="button"
            size="sm"
            variant="ghost"
            className="h-7 px-2"
            onClick={() => setEditing((v) => !v)}
          >
            <Pencil className="mr-1 size-3" />
            {editing ? "预览" : "编辑"}
          </Button>
          {editing ? (
            <Button
              type="button"
              size="sm"
              className="h-7 px-2"
              disabled={saving || !dirty}
              onClick={() => void onSave()}
            >
              <Save className="mr-1 size-3" />
              保存
            </Button>
          ) : null}
        </div>
        <div className="nlm-wiki-body">
          {editing ? (
            <div className="nlm-wiki-editor">
              <Input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                className="nlm-wiki-title-input"
                placeholder="标题"
              />
              <Textarea
                value={content}
                onChange={(e) => setContent(e.target.value)}
                className="nlm-wiki-md"
                placeholder="Markdown，可用 [[其他页]] 互链"
              />
              <p className="nlm-wiki-hint">⌘S / Ctrl+S 保存</p>
            </div>
          ) : (
            <div
              className="nlm-wiki-article"
              onClick={(e) => {
                const a = (e.target as HTMLElement).closest("a");
                const href = a?.getAttribute("href") || "";
                const cite = parseKnowledgeCiteHref(href);
                if (!cite) return;
                e.preventDefault();
                if (cite.section === "wiki") {
                  onOpenSlug(cite.slug);
                  return;
                }
                window.dispatchEvent(new CustomEvent("nlm-knowledge-open", { detail: { href: cite.href } }));
              }}
            >
              <MarkdownBody content={rendered} kbId={kbId} streaming={false} plain={false} />
            </div>
          )}
          <aside className="nlm-wiki-revisions">
            <div className="nlm-knowledge-rail-label">时间线</div>
            {(page.revisions || []).length ? (
              (page.revisions || []).map((rev) => (
                <button
                  key={rev.revision_id}
                  type="button"
                  className="nlm-wiki-rev"
                  onClick={() => setPendingRev(rev)}
                >
                  <History className="size-3 opacity-60" />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate">
                      {rev.author === "user" ? "你" : "代理"} · {rev.message || "保存"}
                    </span>
                    <span className="block text-[10px] text-muted-foreground">
                      {formatRel(rev.created_at)}
                    </span>
                  </span>
                </button>
              ))
            ) : (
              <p className="m-0 px-1 text-[11px] text-muted-foreground">还没有修订</p>
            )}
            {(page.links_out || []).length ? (
              <>
                <div className="nlm-knowledge-rail-label mt-3">出链</div>
                {(page.links_out || []).map((link, i) => (
                  <button
                    key={`${link.to_id}-${i}`}
                    type="button"
                    className="nlm-wiki-rev"
                    onClick={() => {
                      if (link.to_kind === "page" && link.to_id) onOpenSlug(link.to_id);
                    }}
                  >
                    {link.label || link.to_id}
                  </button>
                ))}
              </>
            ) : null}
          </aside>
        </div>
        <AlertDialog open={Boolean(pendingRev)} onOpenChange={(open) => !open && setPendingRev(null)}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>回滚到这个版本？</AlertDialogTitle>
              <AlertDialogDescription>
                {pendingRev
                  ? `${pendingRev.author === "user" ? "你" : "代理"} · ${pendingRev.message || "保存"} · ${formatRel(pendingRev.created_at)}。当前正文会变成该快照，并再记一条修订。`
                  : ""}
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>取消</AlertDialogCancel>
              <AlertDialogAction
                disabled={saving}
                onClick={() => pendingRev && void onRollback(pendingRev.revision_id)}
              >
                回滚
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>
    );
  }

  return (
    <div className="nlm-wiki-pane" data-testid="knowledge-wiki-page">
      <div className="nlm-wiki-toolbar">
        <div className="flex items-center gap-1.5 text-[13px] font-medium">
          <BookOpen className="size-3.5 text-teal" />
          Wiki
        </div>
        <div className="nlm-kb-search">
          <Search className="size-3.5 opacity-50" />
          <Input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="筛选页面"
            className="h-7 border-0 bg-transparent px-1 text-[12px] shadow-none focus-visible:ring-0"
          />
        </div>
        <Button
          type="button"
          size="sm"
          className="h-7 px-2"
          data-testid="knowledge-wiki-distill"
          disabled={distilling}
          onClick={() => void onDistill()}
        >
          <Sparkles className={cn("mr-1 size-3", distilling && "animate-pulse")} />
          {distilling ? "生成中…" : "生成本库 Wiki"}
        </Button>
      </div>
      {loading && !pages.length ? (
        <div className="nlm-wiki-list">
          {[0, 1, 2].map((i) => (
            <div key={i} className="nlm-wiki-skel" />
          ))}
        </div>
      ) : visiblePages.length ? (
        <ul className="nlm-wiki-list">
          <AnimatePresence initial={false}>
            {visiblePages.map((item) => (
              <motion.li
                key={item.page_id}
                layout={!reduced}
                initial={reduced ? false : { opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.18 }}
              >
                <button
                  type="button"
                  className="nlm-wiki-item"
                  data-testid={`knowledge-wiki-item-${item.slug}`}
                  onClick={() => onOpenSlug(item.slug)}
                >
                  <span className="nlm-wiki-item-ico">
                    {item.slug === "_index" ? <Sparkles className="size-3.5" /> : <BookOpen className="size-3.5" />}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium">{item.title}</span>
                    <span className="mt-0.5 flex items-center gap-1.5 text-[10px] text-muted-foreground">
                      <span className="truncate">{item.slug}</span>
                      {item.updated_at ? (
                        <>
                          <Clock3 className="size-2.5" />
                          {formatRel(item.updated_at)}
                        </>
                      ) : null}
                    </span>
                  </span>
                  {item.status === "draft" ? <span className="nlm-knowledge-pill">草稿</span> : null}
                </button>
              </motion.li>
            ))}
          </AnimatePresence>
        </ul>
      ) : (
        <div className="nlm-kb-empty" data-testid="knowledge-wiki-empty">
          <div className="nlm-kb-empty-mark">Wiki</div>
          <p className="nlm-kb-empty-title">{filter ? "没有匹配的页面" : "还没有第二层 Wiki"}</p>
          <p className="nlm-kb-empty-copy">
            {filter
              ? "换个关键词，或清空筛选。"
              : "原文不动。蒸馏会写出可编辑、带 [[链接]] 的互联笔记。没有模型时走规则提纲。"}
          </p>
          {!filter ? (
            <Button type="button" size="sm" disabled={distilling} onClick={() => void onDistill()}>
              <Sparkles className="mr-1 size-3" />
              生成本库 Wiki
            </Button>
          ) : null}
        </div>
      )}
    </div>
  );
}
