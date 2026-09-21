import { Fragment, useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Download } from "lucide-react";

import { getOfficeOutline, postOfficeStyle } from "@/api/endpoints";
import type { CanvasViewProps } from "@/components/canvas/canvasRegistry";
import { Button } from "@/components/ui/button";
import { officeDocIdFromBody } from "@/lib/canvasDoc";
import {
  NLM_OFFICE_WRITING_EVENT,
  officeAlignment,
  officeImageSrc,
  officeMathExportHints,
  splitOfficeMath,
  unwrapOfficeLatex,
  parseOfficeOutline,
  type OfficeOutline,
  type OfficeSlide,
  type OfficeWordBlock,
} from "@/lib/officeOutline";
import {
  formatOfficeCaption,
  layoutFromStyle,
  normalizeOfficeStyleId,
  officeThemeCssVars,
  type OfficeStyleId,
} from "@/lib/officeStyle";
import { applyOfficePreview, emptyOfficePreview } from "@/lib/officePreview";
import { renderLatex } from "@/lib/markdown/math";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

function OfficeRichText({
  text,
  className,
  as: Tag = "span",
}: {
  text: string;
  className?: string;
  as?: "span" | "p" | "li" | "td" | "th" | "h1" | "h2" | "h3" | "h4";
}) {
  const parts = useMemo(() => splitOfficeMath(text), [text]);
  const hasMath = parts.some((part) => part.kind === "math");
  if (!hasMath) {
    return <Tag className={className}>{text}</Tag>;
  }
  return (
    <Tag className={className}>
      {parts.map((part, i) =>
        part.kind === "text" ? (
          <Fragment key={i}>{part.value}</Fragment>
        ) : (
          <OfficeEquation key={i} latex={part.value} display="inline" />
        ),
      )}
    </Tag>
  );
}

function OfficeEquation({
  latex,
  display = "block",
  caption,
  number,
}: {
  latex: string;
  display?: "inline" | "block";
  caption?: string;
  number?: number;
}) {
  const ref = useRef<HTMLElement | null>(null);
  const tex = unwrapOfficeLatex(latex);
  useEffect(() => {
    void renderLatex(ref.current, tex, display !== "inline");
  }, [tex, display]);
  if (display === "inline") {
    return <span ref={ref as never} className="nlm-office-eq-inline" data-testid="office-equation-inline" />;
  }
  return (
    <figure className="nlm-office-eq" data-testid="office-equation">
      <div className="nlm-office-eq-row">
        <div ref={ref as never} className="nlm-office-eq-body" />
        {number ? <span className="nlm-office-eq-no">({number})</span> : null}
      </div>
      {caption ? <figcaption className="nlm-office-caption">{caption}</figcaption> : null}
    </figure>
  );
}

function WordBlockView({
  block,
  caption,
  eqNo,
}: {
  block: OfficeWordBlock;
  caption?: string;
  eqNo?: number;
}) {
  if (block.type === "heading") {
    const Tag = block.level === 1 ? "h1" : block.level === 2 ? "h2" : "h3";
    return <OfficeRichText as={Tag} className={`nlm-office-h${block.level}`} text={block.text} />;
  }
  if (block.type === "paragraph") return <OfficeRichText as="p" className="nlm-office-p" text={block.text} />;
  if (block.type === "equation") {
    return <OfficeEquation latex={block.latex} display={block.display} caption={block.caption} number={eqNo} />;
  }
  if (block.type === "bullet_list" || block.type === "numbered_list") {
    const Tag = block.type === "numbered_list" ? "ol" : "ul";
    return (
      <Tag className="nlm-office-list">
        {block.items.map((item, i) => (
          <OfficeRichText key={i} as="li" className="nlm-office-li" text={item} />
        ))}
      </Tag>
    );
  }
  if (block.type === "quote") {
    return (
      <blockquote className="nlm-office-quote">
        <OfficeRichText text={block.text} />
        {block.attribution ? <cite>— {block.attribution}</cite> : null}
      </blockquote>
    );
  }
  if (block.type === "table") {
    return (
      <div className="nlm-office-table-wrap">
        <table className="nlm-office-table">
          <thead>
            <tr>
              {block.headers.map((h, i) => (
                <th key={i}>
                  <OfficeRichText text={h} />
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {block.rows.map((row, ri) => (
              <tr key={ri}>
                {block.headers.map((_, ci) => (
                    <td key={ci}>
                      <OfficeRichText text={row[ci] || ""} />
                    </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        {caption ? <p className="nlm-office-caption">{caption}</p> : null}
      </div>
    );
  }
  if (block.type === "page_break") return <div className="nlm-office-break">分页</div>;
  if (block.type === "image") {
    const src = officeImageSrc(block);
    return (
      <figure className="nlm-office-figure">
        {src ? <img src={src} alt={block.alt || caption || block.caption || ""} /> : <p className="nlm-office-caption">[图片]</p>}
        {caption || block.caption ? <figcaption className="nlm-office-caption">{caption || block.caption}</figcaption> : null}
      </figure>
    );
  }
  return null;
}

function SlideView({
  slide,
  index,
  total,
  deckTitle,
  sectionNo,
  styleId,
}: {
  slide: OfficeSlide;
  index: number;
  total: number;
  deckTitle: string;
  sectionNo?: number;
  styleId: OfficeStyleId;
}) {
  const footer = (
    <div className="nlm-office-slide-footer">
      <span>{deckTitle}</span>
      <span>
        {index} / {total}
      </span>
    </div>
  );
  if (slide.type === "title") {
    return (
      <article className="nlm-office-slide is-title">
        <div className="nlm-office-slide-accent" />
        <OfficeRichText as="h2" className="nlm-office-slide-title" text={slide.title} />
        <div className="nlm-office-slide-rule" />
        {slide.subtitle ? <OfficeRichText as="p" className="nlm-office-slide-sub" text={slide.subtitle} /> : null}
        {footer}
      </article>
    );
  }
  if (slide.type === "section") {
    return (
      <article className="nlm-office-slide is-section">
        {styleId === "academic" && sectionNo ? (
          <p className="nlm-office-slide-num">{String(sectionNo).padStart(2, "0")}</p>
        ) : (
          <p className="nlm-office-slide-kicker">{slide.kicker || "SECTION"}</p>
        )}
        <OfficeRichText as="h2" className="nlm-office-slide-title" text={slide.title} />
        {footer}
      </article>
    );
  }
  if (slide.type === "quote") {
    return (
      <article className="nlm-office-slide">
        <div className="nlm-office-slide-accent" />
        <OfficeRichText as="p" className="nlm-office-slide-quote" text={slide.text} />
        {slide.attribution ? <p className="nlm-office-slide-sub">— {slide.attribution}</p> : null}
        {footer}
      </article>
    );
  }
  if (slide.type === "two_column") {
    return (
      <article className="nlm-office-slide">
        <div className="nlm-office-slide-accent" />
        <OfficeRichText as="h2" className="nlm-office-slide-title" text={slide.title} />
        <div className="nlm-office-slide-rule" />
        <div className="nlm-office-cols">
          {[slide.left, slide.right].map((col, i) => (
            <div key={i} className="nlm-office-col">
              {col?.heading ? <OfficeRichText as="h4" text={col.heading} /> : null}
              {col?.body ? <OfficeRichText as="p" className="nlm-office-p" text={col.body} /> : null}
              {col?.items?.length ? (
                <ul className="nlm-office-slide-list">
                  {col.items.map((it, j) => (
                    <OfficeRichText key={j} as="li" text={it} />
                  ))}
                </ul>
              ) : null}
            </div>
          ))}
        </div>
        {footer}
      </article>
    );
  }
  if (slide.type === "image") {
    const src = officeImageSrc(slide);
    return (
      <article className="nlm-office-slide">
        <div className="nlm-office-slide-accent" />
        {slide.title ? <OfficeRichText as="h2" className="nlm-office-slide-title" text={slide.title} /> : null}
        <figure className="nlm-office-figure">
          {src ? <img src={src} alt={slide.caption || slide.title || ""} /> : null}
          {slide.caption ? <figcaption className="nlm-office-caption">{slide.caption}</figcaption> : null}
        </figure>
        {footer}
      </article>
    );
  }
  if (slide.type === "equation") {
    return (
      <article className="nlm-office-slide is-equation">
        <div className="nlm-office-slide-accent" />
        {slide.title ? <OfficeRichText as="h2" className="nlm-office-slide-title" text={slide.title} /> : null}
        {slide.title ? <div className="nlm-office-slide-rule" /> : null}
        <OfficeEquation latex={slide.latex} display="block" caption={slide.caption} />
        {footer}
      </article>
    );
  }
  return (
    <article className="nlm-office-slide">
      <div className="nlm-office-slide-accent" />
      <OfficeRichText as="h2" className="nlm-office-slide-title" text={slide.type === "bullets" ? slide.title : ""} />
      <div className="nlm-office-slide-rule" />
      {slide.type === "bullets" ? (
        <ul className="nlm-office-slide-list">
          {slide.items.map((it, i) => (
            <OfficeRichText key={i} as="li" text={it} />
          ))}
        </ul>
      ) : null}
      {footer}
    </article>
  );
}

export function OfficeCanvasView({ doc, onCommit }: CanvasViewProps) {
  const [preview, setPreview] = useState(() =>
    applyOfficePreview(emptyOfficePreview(), { outline: parseOfficeOutline(doc.body) }),
  );
  const [writing, setWriting] = useState(false);
  const [styleBusy, setStyleBusy] = useState(false);
  const stageRef = useRef<HTMLDivElement | null>(null);
  const lastAnchor = useRef<string>("");

  useEffect(() => {
    const parsed = parseOfficeOutline(doc.body);
    if (!parsed) return;
    setPreview((prev) => applyOfficePreview(prev, { outline: parsed, op: parsed.last_op }));
    setWriting(false);
  }, [doc.body]);

  useEffect(() => {
    if (parseOfficeOutline(doc.body)) return;
    const id = officeDocIdFromBody(doc.body) || (String(doc.source || "").startsWith("off_") ? String(doc.source) : "");
    if (!id) return;
    let cancelled = false;
    void getOfficeOutline(id)
      .then((data) => {
        if (cancelled || !data?.outline) return;
        onCommit(JSON.stringify(data.outline));
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [doc.body, doc.source, onCommit]);

  useEffect(() => {
    const onWrite = () => setWriting(true);
    window.addEventListener(NLM_OFFICE_WRITING_EVENT, onWrite);
    return () => window.removeEventListener(NLM_OFFICE_WRITING_EVENT, onWrite);
  }, []);

  const outline = preview.outline;
  const align = useMemo(() => (outline ? officeAlignment(outline) : null), [outline]);
  const entering = useMemo(() => new Set(preview.enteringIds), [preview.enteringIds]);

  useEffect(() => {
    const ids = preview.enteringIds;
    const last = ids[ids.length - 1];
    if (!last || last === lastAnchor.current) return;
    lastAnchor.current = last;
    const node = stageRef.current?.querySelector(`[data-office-id="${last}"]`);
    node?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [preview.enteringIds]);

  const kindLabel = outline?.kind === "pptx" ? "PowerPoint" : "Word";
  const mathHints = useMemo(() => (outline ? officeMathExportHints(outline) : []), [outline]);
  const downloadUrl = outline?.download_url || (outline?.doc_id ? `/api/office/files/${outline.doc_id}` : "");
  const fileName = outline?.file_name || (outline?.kind === "pptx" ? `${outline?.title || "deck"}.pptx` : `${outline?.title || "document"}.docx`);
  const styleId = normalizeOfficeStyleId(outline?.style_id);
  const pack = layoutFromStyle(styleId);
  const themeVars = officeThemeCssVars(outline?.theme || {});

  const download = () => {
    if (!downloadUrl) return;
    const a = document.createElement("a");
    a.href = downloadUrl;
    a.download = fileName;
    a.click();
  };

  const applyStyle = (next: OfficeStyleId) => {
    if (!outline?.doc_id || next === styleId || styleBusy) return;
    setStyleBusy(true);
    void postOfficeStyle({ doc_id: outline.doc_id, style_id: next })
      .then((data) => {
        if (data?.outline) onCommit(JSON.stringify(data.outline));
        else toast.error("换风格没有返回新大纲");
      })
      .catch((err: unknown) => {
        toast.error(String((err as Error)?.message || err || "换风格失败"));
      })
      .finally(() => setStyleBusy(false));
  };

  if (!outline) {
    return (
      <div className="nlm-office-view" data-style="commercial" data-testid="office-canvas">
        <div className="flex flex-1 items-center justify-center px-4 text-center text-[12px] text-muted-foreground">
          文档预览未就绪。点顶栏 Canvas 可恢复上次大纲；若磁盘上已有 .docx/.pptx，会从 outline JSON 重新打开。
        </div>
      </div>
    );
  }

  const items = outline.kind === "pptx" ? outline.slides || [] : outline.blocks || [];

  return (
    <div
      className="nlm-office-view"
      data-style={styleId}
      data-testid="office-canvas"
      style={themeVars as CSSProperties}
    >
      <div className="nlm-office-toolbar">
        <span className="nlm-office-kicker">{kindLabel}</span>
        <span className="min-w-0 truncate text-[12px] font-medium">{outline.title || "未命名"}</span>
        {writing ? (
          <span className="nlm-office-writing" data-testid="office-writing">
            <span className="nlm-office-writing-dot" />
            正在写入…
          </span>
        ) : (
          <span className="nlm-office-meta">
            {align ? `${align.filledPlan}/${align.totalPlan || 0} 节` : ""}
            {outline.path ? ` · ${outline.path}` : ""}
          </span>
        )}
        <div className="ml-auto flex items-center gap-2">
          <div className="nlm-office-style" data-testid="office-style" role="group" aria-label="文档风格">
            <button
              type="button"
              className={cn("nlm-office-style-pill", styleId === "commercial" && "is-active")}
              data-testid="office-style-commercial"
              disabled={!outline.doc_id || styleBusy}
              onClick={() => applyStyle("commercial")}
            >
              商业风
            </button>
            <button
              type="button"
              className={cn("nlm-office-style-pill", styleId === "academic" && "is-active")}
              data-testid="office-style-academic"
              disabled={!outline.doc_id || styleBusy}
              onClick={() => applyStyle("academic")}
            >
              学术风
            </button>
          </div>
          <Button
            type="button"
            size="sm"
            variant="secondary"
            className="h-6 gap-1 px-2 text-[11px]"
            disabled={!downloadUrl}
            data-testid="office-download"
            onClick={download}
          >
            <Download className="size-3" />
            下载
          </Button>
        </div>
      </div>
      {mathHints.length ? (
        <div className="nlm-office-export-hint" data-testid="office-math-export-hint">
          {mathHints.join(" ")}
        </div>
      ) : null}

      <div className="nlm-office-body">
        <aside className="nlm-office-rail" aria-label="文档结构" data-testid="office-structure">
          <p className="nlm-office-rail-title">结构</p>
          {outline.throughline ? (
            <p className="nlm-office-throughline" data-testid="office-throughline">
              {outline.throughline}
            </p>
          ) : null}
          <ol className="nlm-office-plan">
            {(align?.plan || []).map((row) => (
              <li key={row.id} className={cn("nlm-office-plan-item", row.filled && "is-filled")}>
                <span className="nlm-office-plan-mark">{row.filled ? "✓" : "○"}</span>
                <span>{row.title}</span>
              </li>
            ))}
          </ol>
        </aside>

        <div className="nlm-office-stage" ref={stageRef}>
          {outline.kind === "docx" ? (
            <div className="nlm-office-page">
              {pack.word_header_title ? <p className="nlm-office-page-header">{outline.title}</p> : null}
              <AnimatePresence initial={false}>
                {(() => {
                  let fig = 0;
                  let tbl = 0;
                  let eq = 0;
                  return (outline.blocks || []).map((block) => {
                    let caption: string | undefined;
                    let eqNo: number | undefined;
                    if (block.type === "image") {
                      fig += 1;
                      caption = formatOfficeCaption("图", fig, block.caption, pack.caption_numbers);
                    } else if (block.type === "table") {
                      tbl += 1;
                      caption = formatOfficeCaption("表", tbl, undefined, pack.caption_numbers);
                    } else if (block.type === "equation" && block.display !== "inline") {
                      eq += 1;
                      if (pack.equation_numbers) eqNo = eq;
                    }
                    return (
                      <motion.div
                        key={block.id}
                        data-office-id={block.id}
                        className={cn(entering.has(block.id) && "nlm-office-block-enter")}
                        initial={entering.has(block.id) ? { opacity: 0, y: 10 } : false}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.38, ease: [0.22, 1, 0.36, 1] }}
                      >
                        <WordBlockView block={block} caption={caption} eqNo={eqNo} />
                      </motion.div>
                    );
                  });
                })()}
              </AnimatePresence>
              {pack.word_footer_page ? <p className="nlm-office-page-footer">1</p> : null}
            </div>
          ) : (
            <div className="nlm-office-slide-stack">
              {(() => {
                let sectionNo = 0;
                return (outline.slides || []).map((slide, i) => {
                  if (slide.type === "section") sectionNo += 1;
                  return (
                    <div key={slide.id} data-office-id={slide.id}>
                      <motion.div
                        className={cn(entering.has(slide.id) && "nlm-office-block-enter")}
                        initial={entering.has(slide.id) ? { opacity: 0, y: 14 } : false}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
                      >
                        <SlideView
                          slide={slide}
                          index={i + 1}
                          total={(outline.slides || []).length}
                          deckTitle={outline.title}
                          sectionNo={slide.type === "section" ? sectionNo : 0}
                          styleId={styleId}
                        />
                      </motion.div>
                      {slide.notes ? <p className="nlm-office-notes">讲稿 · {slide.notes}</p> : null}
                    </div>
                  );
                });
              })()}
            </div>
          )}
          {!items.length ? (
            <p className="m-0 pt-8 text-center text-[12px] text-muted-foreground">结构已就绪，正在等待写入…</p>
          ) : null}
        </div>
      </div>
    </div>
  );
}

export default OfficeCanvasView;
