import { useEffect, useMemo, useRef, useState } from "react";
import { FileText, Network, Search, Sparkles } from "lucide-react";
import { toast } from "sonner";

import { getKnowledgeGraph, type GraphEdge, type GraphNode } from "@/api/endpoints";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

export type GraphLayerProps = {
  kbId: string;
  remote?: boolean;
  onOpenWiki: (slug: string) => void;
  onOpenDoc: (docId: string) => void;
  onGenerateWiki?: () => void;
};

const KIND_LABEL: Record<string, string> = {
  entity: "实体",
  page: "Wiki",
  doc: "原文",
};

type KindFilter = "entity" | "page" | "doc";

export function GraphLayer({
  kbId,
  remote = false,
  onOpenWiki,
  onOpenDoc,
  onGenerateWiki,
}: GraphLayerProps) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [edges, setEdges] = useState<GraphEdge[]>([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [kinds, setKinds] = useState<Record<KindFilter, boolean>>({
    entity: true,
    page: true,
    doc: true,
  });
  const [hover, setHover] = useState<GraphNode | null>(null);
  const [picked, setPicked] = useState<GraphNode | null>(null);

  const load = async (q = query) => {
    if (remote || !kbId) {
      setNodes([]);
      setEdges([]);
      return;
    }
    setLoading(true);
    try {
      const data = await getKnowledgeGraph({ kb_id: kbId, q: q || undefined, limit: 80 });
      setNodes(data.nodes || []);
      setEdges(data.edges || []);
    } catch (err: any) {
      toast.error(String(err?.message || err || "加载图谱失败"));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load("");
  }, [kbId, remote]);

  const visible = useMemo(() => {
    const allow = new Set(
      (Object.keys(kinds) as KindFilter[]).filter((k) => kinds[k]),
    );
    const next = nodes.filter((n) => allow.has((n.kind as KindFilter) || "entity"));
    const ids = new Set(next.map((n) => n.node_id));
    return {
      nodes: next,
      edges: edges.filter((e) => ids.has(e.from_id) && ids.has(e.to_id)),
    };
  }, [nodes, edges, kinds]);

  const focus = hover || picked;

  useEffect(() => {
    const el = hostRef.current;
    if (!el || !visible.nodes.length) return;
    let chart: { dispose: () => void; resize: () => void } | null = null;
    let cancelled = false;
    const onResize = () => chart?.resize();
    void (async () => {
      const echarts = await import("echarts");
      if (cancelled || !hostRef.current) return;
      const inst = echarts.init(hostRef.current);
      chart = inst;
      const styles = getComputedStyle(hostRef.current);
      const fg = styles.getPropertyValue("--foreground").trim() || "220 14% 96%";
      const muted = styles.getPropertyValue("--muted-foreground").trim() || "220 10% 70%";
      inst.setOption({
        backgroundColor: "transparent",
        tooltip: { show: false },
        legend: { show: false },
        series: [
          {
            type: "graph",
            layout: "force",
            roam: true,
            draggable: true,
            data: visible.nodes.map((n) => ({
              id: n.node_id,
              name: n.label || n.node_id,
              category: n.kind === "entity" ? 0 : n.kind === "page" ? 1 : 2,
              symbolSize: n.kind === "page" ? 30 : n.kind === "doc" ? 22 : 16,
              itemStyle: {
                shadowBlur: n.kind === "page" ? 12 : 0,
                shadowColor: "rgba(45, 212, 191, 0.35)",
              },
            })),
            links: visible.edges.map((e) => ({
              source: e.from_id,
              target: e.to_id,
              value: e.rel,
            })),
            categories: [
              { name: "实体", itemStyle: { color: "#94a3b8" } },
              { name: "Wiki", itemStyle: { color: "#2dd4bf" } },
              { name: "原文", itemStyle: { color: "#60a5fa" } },
            ],
            force: { repulsion: 260, edgeLength: [70, 140], gravity: 0.08 },
            label: {
              show: true,
              fontSize: 10,
              color: `hsl(${fg})`,
            },
            lineStyle: { opacity: 0.4, curveness: 0.12, color: `hsl(${muted})` },
            emphasis: {
              focus: "adjacency",
              label: { fontSize: 12 },
              lineStyle: { width: 2, opacity: 0.85 },
            },
          },
        ],
      });
      inst.off("click");
      inst.off("mouseover");
      inst.off("mouseout");
      inst.on("mouseover", (ev) => {
        const data = ev?.data as { id?: string } | undefined;
        const hit = visible.nodes.find((n) => n.node_id === String(data?.id || ""));
        if (hit) setHover(hit);
      });
      inst.on("mouseout", () => setHover(null));
      inst.on("click", (ev) => {
        const data = ev?.data as { id?: string } | undefined;
        const id = String(data?.id || "");
        const hit = visible.nodes.find((n) => n.node_id === id);
        if (!hit) return;
        setPicked(hit);
        const slug = String((hit.attrs as { slug?: string } | undefined)?.slug || "");
        if (hit.kind === "page" && (slug || hit.page_id)) {
          onOpenWiki(slug || String(hit.page_id || ""));
          return;
        }
        if (hit.kind === "doc" && hit.doc_id) onOpenDoc(hit.doc_id);
      });
    })();
    window.addEventListener("resize", onResize);
    return () => {
      cancelled = true;
      window.removeEventListener("resize", onResize);
      chart?.dispose();
    };
  }, [visible.nodes, visible.edges, onOpenDoc, onOpenWiki]);

  const toggleKind = (id: KindFilter) => {
    setKinds((prev) => {
      const next = { ...prev, [id]: !prev[id] };
      if (!next.entity && !next.page && !next.doc) return prev;
      return next;
    });
  };

  if (remote) {
    return (
      <div className="nlm-graph-pane" data-testid="knowledge-graph-page">
        <div className="nlm-kb-empty">
          <div className="nlm-kb-empty-mark">Graph</div>
          <p className="nlm-kb-empty-title">图谱只画本机 Wiki</p>
          <p className="nlm-kb-empty-copy">远程库不会在 NLM 里蒸第二层。</p>
        </div>
      </div>
    );
  }

  return (
    <div className="nlm-graph-pane" data-testid="knowledge-graph-page">
      <div className="nlm-wiki-toolbar">
        <div className="flex items-center gap-1.5 text-[13px] font-medium">
          <Network className="size-3.5 text-teal" />
          图谱
        </div>
        <div className="nlm-kb-search">
          <Search className="size-3.5 opacity-50" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="搜节点，回车过滤"
            className="h-7 border-0 bg-transparent px-1 text-[12px] shadow-none focus-visible:ring-0"
            onKeyDown={(e) => {
              if (e.key === "Enter") void load();
            }}
          />
        </div>
        <div className="nlm-graph-filters">
          {(Object.keys(KIND_LABEL) as KindFilter[]).map((id) => (
            <button
              key={id}
              type="button"
              className={cn("nlm-graph-chip", `is-${id}`, kinds[id] && "is-on")}
              onClick={() => toggleKind(id)}
            >
              {KIND_LABEL[id]}
            </button>
          ))}
        </div>
      </div>
      {!nodes.length ? (
        <div className="nlm-kb-empty" data-testid="knowledge-graph-empty">
          <div className="nlm-kb-empty-mark">Graph</div>
          <p className="nlm-kb-empty-title">{loading ? "正在铺开节点…" : "图谱还是空的"}</p>
          <p className="nlm-kb-empty-copy">
            先蒸馏 Wiki。实体、页面和原文会画在这里；点 Wiki 进页，点原文回文档库。
          </p>
          {onGenerateWiki && !loading ? (
            <Button type="button" size="sm" onClick={onGenerateWiki}>
              <Sparkles className="mr-1 size-3" />
              去生成 Wiki
            </Button>
          ) : null}
        </div>
      ) : (
        <>
          <div className="nlm-graph-canvas" ref={hostRef} />
          <div className="nlm-graph-dock">
            <div className="min-w-0 flex-1">
              {focus ? (
                <>
                  <div className="flex items-center gap-1.5 text-[12px] font-medium">
                    <span className={cn("nlm-graph-chip is-on", `is-${focus.kind}`)}>
                      {KIND_LABEL[focus.kind || ""] || focus.kind}
                    </span>
                    <span className="truncate">{focus.label}</span>
                  </div>
                  <p className="m-0 mt-0.5 text-[11px] text-muted-foreground">
                    {focus.kind === "page"
                      ? "点击打开 Wiki 页"
                      : focus.kind === "doc"
                        ? "点击打开原文预览"
                        : "实体节点，沿边看邻居"}
                  </p>
                </>
              ) : (
                <p className="m-0 text-[11px] text-muted-foreground">
                  {visible.nodes.length} 个节点 · {visible.edges.length} 条边 · 拖拽画布，悬停看邻接
                </p>
              )}
            </div>
            {focus?.kind === "page" ? (
              <Button
                type="button"
                size="sm"
                variant="secondary"
                className="h-7"
                onClick={() => {
                  const slug = String((focus.attrs as { slug?: string } | undefined)?.slug || focus.page_id || "");
                  if (slug) onOpenWiki(slug);
                }}
              >
                打开 Wiki
              </Button>
            ) : null}
            {focus?.kind === "doc" && focus.doc_id ? (
              <Button
                type="button"
                size="sm"
                variant="secondary"
                className="h-7"
                onClick={() => onOpenDoc(focus.doc_id || "")}
              >
                <FileText className="mr-1 size-3" />
                打开原文
              </Button>
            ) : null}
          </div>
        </>
      )}
    </div>
  );
}
