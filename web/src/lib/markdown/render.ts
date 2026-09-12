import { marked } from "marked";
import DOMPurify from "dompurify";
import { openMermaidFullscreen } from "./mermaidFullscreen";
import { drawioMarkdownHtml, isDrawioLang, looksLikeDrawioXml, renderDrawioIn } from "./drawio";
import {
  echartsMarkdownHtml,
  isEchartsLang,
  looksLikeEchartsOption,
  normalizeEchartsMarkdown,
} from "./echarts";
import { applyMathPlaceholders, protectMath } from "./math";
import { enhanceChatImages } from "./chatImages";
import { diagramInk, diagramPanelBg, mermaidThemeName } from "./diagramTheme";
import { isMindmapLang, mindmapMarkdownHtml, renderMindmapIn } from "./mindmap";

export { enhanceChatImages } from "./chatImages";
export { renderMindmapIn };

function escapeHtml(s: string) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

const renderer = new marked.Renderer();
const baseCode =
  typeof (renderer as any).code === "function" ? (renderer as any).code.bind(renderer) : null;

(renderer as any).code = function codeToken(token: any, infoOrLang?: any, escaped?: any) {
  let text: string;
  let lang: string;
  if (token && typeof token === "object" && "text" in token) {
    text = token.text || "";
    lang = (token.lang || "").trim().split(/\s+/)[0] || "";
  } else {
    text = String(token || "");
    lang =
      String(infoOrLang || "")
        .trim()
        .split(/\s+/)[0] || "";
  }
  const langKey = lang.toLowerCase();
  if (langKey === "mermaid") {
    return `<div class="mermaid-block" data-mermaid-host="1"><pre class="mermaid">${escapeHtml(text)}</pre></div>`;
  }
  if (
    isEchartsLang(langKey) ||
    ((langKey === "json" || langKey === "javascript" || langKey === "js") &&
      looksLikeEchartsOption(text))
  ) {
    return echartsMarkdownHtml(text);
  }
  if (isDrawioLang(langKey) || (langKey === "xml" && looksLikeDrawioXml(text))) {
    return drawioMarkdownHtml(text);
  }
  if (isMindmapLang(langKey)) {
    return mindmapMarkdownHtml(text);
  }
  if (baseCode) {
    if (token && typeof token === "object" && "text" in token) {
      return baseCode(token);
    }
    return baseCode(token, infoOrLang, escaped);
  }
  const cls = lang ? ` class="language-${escapeHtml(lang)}"` : "";
  return `<pre><code${cls}>${escapeHtml(text)}</code></pre>`;
};

marked.setOptions({
  gfm: true,
  breaks: true,
  // @ts-expect-error marked option legacy
  headerIds: false,
  mangle: false,
  renderer,
});

function sanitizeHtml(html: string) {
  return DOMPurify.sanitize(html, {
    USE_PROFILES: { html: true },
    ADD_ATTR: [
      "target",
      "rel",
      "class",
      "style",
      "data-mermaid-host",
      "data-mermaid-zoom",
      "data-mermaid-action",
      "data-echarts-host",
      "data-echarts-zoom",
      "data-echarts-action",
      "data-drawio-host",
      "data-drawio-action",
      "data-mindmap-host",
      "data-mindmap-action",
      "data-node-id",
      "data-code-action",
      "data-mode",
      "data-lang",
      "data-collapsed",
      "title",
      "aria-label",
      "aria-expanded",
      "aria-hidden",
      "type",
      "hidden",
      "viewBox",
      "fill",
      "stroke",
      "stroke-width",
      "stroke-linecap",
      "stroke-linejoin",
      "width",
      "height",
      "x",
      "y",
      "rx",
      "x1",
      "y1",
      "x2",
      "y2",
      "points",
      "d",
      "xmlns",
    ],
    ADD_TAGS: [
      "div",
      "button",
      "span",
      "pre",
      "svg",
      "path",
      "rect",
      "polyline",
      "line",
      "figure",
      "figcaption",
      "a",
      "math",
      "semantics",
      "mrow",
      "mi",
      "mo",
      "mn",
      "msup",
      "msub",
      "msubsup",
      "mfrac",
      "msqrt",
      "mroot",
      "mtable",
      "mtr",
      "mtd",
      "mtext",
      "annotation",
    ],
  });
}

/** Sync markdown → HTML (math left as %%NLM_MATH_n%% placeholders). */
export function renderMarkdown(text: string, { streaming = false }: { streaming?: boolean } = {}) {
  const normalized = normalizeEchartsMarkdown(text || "");
  const { text: protectedMd } = protectMath(normalized);
  let html = marked.parse(protectedMd) as string;
  html = sanitizeHtml(html);
  if (streaming) html += '<span class="streaming-caret" aria-hidden="true"></span>';
  return html;
}

/** Full pipeline including KaTeX (preferred for chat body). */
export async function renderMarkdownWithMath(
  text: string,
  { streaming = false }: { streaming?: boolean } = {}
) {
  const normalized = normalizeEchartsMarkdown(text || "");
  const { text: protectedMd, slots } = protectMath(normalized);
  let html = marked.parse(protectedMd) as string;
  html = sanitizeHtml(html);
  html = await applyMathPlaceholders(html, slots);
  // Sanitize again after KaTeX injects spans
  html = sanitizeHtml(html);
  if (streaming) html += '<span class="streaming-caret" aria-hidden="true"></span>';
  return html;
}

export function decorateMarkdownLinks(root: HTMLElement | null) {
  if (!root) return;
  root.querySelectorAll("a[href]").forEach((a) => {
    (a as HTMLAnchorElement).target = "_blank";
    (a as HTMLAnchorElement).rel = "noopener noreferrer";
  });
}

let mermaidReady: Promise<any> | null = null;
let mermaidRenderSeq = 0;
let mermaidThemeApplied: string | null = null;

function cleanupMermaidArtifacts(id: string) {
  const candidates = [id, `d${id}`, `${id}-svg`, `d${id}-svg`];
  for (const cid of candidates) {
    try {
      document.getElementById(cid)?.remove();
    } catch {
      /* ignore */
    }
  }
  // Mermaid sometimes leaves error SVGs / temp nodes on body
  document.querySelectorAll(`[id^="d${id}"], [id^="${id}"]`).forEach((el) => {
    if ((el as HTMLElement).closest?.(".mermaid-stage, .mermaid-block, .mermaid-fs-overlay")) {
      return;
    }
    try {
      el.remove();
    } catch {
      /* ignore */
    }
  });
}

function isMermaidErrorSvg(svg: string) {
  return /Syntax error in text|mermaid version\s*\d|aria-roledescription=["']error["']|class=["'][^"']*error-icon/i.test(
    svg || ""
  );
}

async function ensureMermaid() {
  if (!mermaidReady) {
    mermaidReady = import("mermaid").then((mod) => {
      const mermaid = (mod as any).default || mod;
      return mermaid;
    });
  }
  const mermaid = await mermaidReady;
  const theme = mermaidThemeName();
  if (mermaidThemeApplied !== theme) {
    mermaid.initialize({
      startOnLoad: false,
      theme,
      securityLevel: "loose",
      // Throw instead of injecting the giant "Syntax error in text" SVG
      suppressErrorRendering: true,
      fontFamily: "IBM Plex Sans, PingFang SC, Microsoft YaHei, sans-serif",
      flowchart: { htmlLabels: true, curve: "basis" },
    });
    mermaidThemeApplied = theme;
  }
  return mermaid;
}

function decodeEntities(s: string) {
  return String(s || "")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&amp;/g, "&")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'");
}

/** Fix common model Mermaid typos without breaking valid arrows like `-.->`. */
export function sanitizeMermaidSource(raw: string) {
  let s = decodeEntities(String(raw || "")).replace(/\r\n/g, "\n").trim();
  s = s.replace(/^```mermaid\s*/i, "").replace(/```\s*$/i, "").trim();
  s = s.replace(/^architecture(\s)/im, "architecture-beta$1");

  // Unicode / fullwidth punctuation that breaks the lexer
  s = s.replace(/[→⟶➜⇨]/g, "-->");
  s = s.replace(/[｜]/g, "|");
  s = s.replace(/[“”]/g, '"').replace(/[‘’]/g, "'");

  if (/^(flowchart|graph)\b/im.test(s)) {
    // Models often emit broken dotted arrows: "-. -->" / "-. -- >"
    s = s.replace(/-\.\s*-+\s*>/g, "-.->");
    // "-.-> |label|" → "-.->|label|"
    s = s.replace(/-\.->\s+\|/g, "-.->|");
    // "--> |label|" → "-->|label|"
    s = s.replace(/-->\s+\|/g, "-->|");
    // Thick/dotted with spaces: "== >" / "-- >" (not already part of -.->)
    s = s.replace(/([^-\s.])\s+--\s*>/g, "$1 --> ");
    // Bare "A -> B" (single dash) → "A --> B"; do NOT touch "-->" / "-.->" / "==>"
    s = s.replace(/([^-=.\s])\s+->\s*(?!>)/g, "$1 --> ");
    // Collapse accidental doubles
    s = s.replace(/-->\s*-->/g, "-->");
    s = s.replace(/-\.->\s*-\.->/g, "-.->");
  }
  return s.trim();
}

export function extractMermaidSource(text: string) {
  const raw = String(text || "").trim();
  const fenced = raw.match(/```mermaid\s*([\s\S]*?)```/i);
  if (fenced) return sanitizeMermaidSource(fenced[1]);
  return sanitizeMermaidSource(raw);
}

function formatMermaidError(err: any): string {
  if (err == null || err === "") return "未知错误";
  if (typeof err === "string") return err.trim();
  const parts: string[] = [];
  if (err.str) parts.push(String(err.str));
  if (err.message) parts.push(String(err.message));
  if (err.hash?.text) parts.push(String(err.hash.text));
  if (err.hash?.token) parts.push(`token: ${err.hash.token}`);
  if (err.hash?.line != null) parts.push(`line ${err.hash.line}`);
  if (err.cause) parts.push(formatMermaidError(err.cause));
  const joined = parts.filter(Boolean).join(" · ");
  return (joined || String(err)).replace(/\s+/g, " ").trim();
}

function shortMermaidError(err: any, max = 72) {
  const full = typeof err === "string" ? err : formatMermaidError(err);
  if (full.length <= max) return full;
  return `${full.slice(0, max - 1)}…`;
}

async function tryParse(mermaid: any, source: string) {
  if (typeof mermaid.parse !== "function") return { ok: true, error: null };
  try {
    const ret = mermaid.parse(source);
    if (ret && typeof ret.then === "function") await ret;
    return { ok: true, error: null };
  } catch (err) {
    return { ok: false, error: err };
  }
}

function iconSvg(name: string) {
  const common =
    'width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"';
  if (name === "copy") {
    return `<svg ${common}><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>`;
  }
  if (name === "fullscreen") {
    return `<svg ${common}><polyline points="15 3 21 3 21 9"/><polyline points="9 21 3 21 3 15"/><line x1="21" y1="3" x2="14" y2="10"/><line x1="3" y1="21" x2="10" y2="14"/></svg>`;
  }
  if (name === "retry") {
    return `<svg ${common}><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>`;
  }
  if (name === "fold") {
    return `<svg ${common} class="icon-chevron"><polyline points="6 9 12 15 18 9"/></svg>`;
  }
  if (name === "minus") {
    return `<svg ${common}><line x1="5" y1="12" x2="19" y2="12"/></svg>`;
  }
  if (name === "plus") {
    return `<svg ${common}><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>`;
  }
  if (name === "download") {
    return `<svg ${common}><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>`;
  }
  return "";
}

function ensureMermaidChrome(block: HTMLElement, source: string) {
  block.dataset.mermaidSource = source;
  if (!block.querySelector(".mermaid-toolbar")) {
    const bar = document.createElement("div");
    bar.className = "mermaid-toolbar";
    bar.innerHTML = `
      <button type="button" class="mermaid-tool-btn icon-btn" data-mermaid-action="fold" title="折叠/展开" aria-label="折叠">${iconSvg("fold")}</button>
      <span class="mermaid-status-inline" hidden></span>
      <span class="mermaid-toolbar-spacer"></span>
      <button type="button" class="mermaid-tool-btn icon-btn" data-mermaid-action="copy" title="复制源码" aria-label="复制">${iconSvg("copy")}</button>
      <button type="button" class="mermaid-tool-btn icon-btn" data-mermaid-action="download-svg" title="下载 SVG" aria-label="下载 SVG">${iconSvg("download")}</button>
      <button type="button" class="mermaid-tool-btn icon-btn" data-mermaid-action="download-png" title="下载 PNG" aria-label="下载 PNG">${iconSvg("download")}</button>
      <button type="button" class="mermaid-tool-btn icon-btn" data-mermaid-action="fullscreen" title="全屏" aria-label="全屏">${iconSvg("fullscreen")}</button>
      <button type="button" class="mermaid-zoom-btn icon-btn" data-mermaid-zoom="out" title="缩小" aria-label="缩小">${iconSvg("minus")}</button>
      <button type="button" class="mermaid-zoom-btn icon-btn" data-mermaid-zoom="in" title="放大" aria-label="放大">${iconSvg("plus")}</button>
      <button type="button" class="mermaid-tool-btn icon-btn" data-mermaid-action="retry" title="重新渲染" aria-label="重试">${iconSvg("retry")}</button>
      <span class="mermaid-mode-switch" role="group" aria-label="视图切换">
        <button type="button" class="mermaid-mode-btn is-active" data-mermaid-action="mode-view">视图</button>
        <button type="button" class="mermaid-mode-btn" data-mermaid-action="mode-source">源码</button>
      </span>
    `;
    block.insertBefore(bar, block.firstChild);
  }
  if (!block.querySelector(".mermaid-viewport")) {
    const viewport = document.createElement("div");
    viewport.className = "mermaid-viewport";
    const stage = document.createElement("div");
    stage.className = "mermaid-stage";
    const pre = block.querySelector("pre.mermaid") as HTMLElement | null;
    if (pre) {
      pre.classList.add("mermaid-source");
      pre.hidden = true;
      block.appendChild(pre);
    }
    viewport.appendChild(stage);
    block.appendChild(viewport);
  } else if (!block.querySelector(".mermaid-stage")) {
    const viewport = block.querySelector(".mermaid-viewport")!;
    const stage = document.createElement("div");
    stage.className = "mermaid-stage";
    const pre = viewport.querySelector("pre.mermaid") as HTMLElement | null;
    if (pre) {
      pre.classList.add("mermaid-source");
      pre.hidden = true;
      block.appendChild(pre);
    }
    viewport.appendChild(stage);
  }
  let sourcePre = block.querySelector("pre.mermaid-source, pre.mermaid") as HTMLElement | null;
  if (!sourcePre) {
    sourcePre = document.createElement("pre");
    sourcePre.className = "mermaid mermaid-source";
    sourcePre.hidden = true;
    block.appendChild(sourcePre);
  }
  sourcePre.textContent = source;
  sourcePre.classList.add("mermaid-source");
  block.querySelectorAll(".mermaid-status").forEach((el) => el.remove());

  if (!block.dataset.zoom) block.dataset.zoom = "1";
  if (!block.dataset.mode) block.dataset.mode = "view";
  applyMermaidZoom(block, Number(block.dataset.zoom) || 1);
  applyMermaidMode(block, block.dataset.mode || "view");
  applyMermaidCollapsed(block, block.dataset.collapsed === "1");
  return block.querySelector(".mermaid-stage") as HTMLElement;
}

function applyMermaidCollapsed(block: HTMLElement, collapsed: boolean) {
  block.dataset.collapsed = collapsed ? "1" : "0";
  block.classList.toggle("is-collapsed", !!collapsed);
  const foldBtn = block.querySelector('[data-mermaid-action="fold"]') as HTMLElement | null;
  if (foldBtn) {
    foldBtn.title = collapsed ? "展开" : "折叠";
    foldBtn.setAttribute("aria-expanded", collapsed ? "false" : "true");
  }
  if (collapsed) {
    const viewport = block.querySelector(".mermaid-viewport") as HTMLElement | null;
    const sourcePre = block.querySelector("pre.mermaid-source") as HTMLElement | null;
    if (viewport) viewport.hidden = true;
    if (sourcePre) {
      sourcePre.hidden = true;
      sourcePre.classList.remove("is-visible");
    }
  } else {
    applyMermaidMode(block, block.dataset.mode || "view");
  }
}

function applyMermaidZoom(block: HTMLElement, zoom: number) {
  const z = Math.min(3, Math.max(0.4, zoom));
  block.dataset.zoom = String(z);
  const stage = block.querySelector(".mermaid-stage") as HTMLElement | null;
  if (stage) {
    stage.style.transform = `scale(${z})`;
    stage.style.transformOrigin = "top center";
  }
}

function applyMermaidMode(block: HTMLElement, mode: string) {
  if (block.dataset.collapsed === "1") return;
  const next = mode === "source" ? "source" : "view";
  block.dataset.mode = next;
  const viewport = block.querySelector(".mermaid-viewport") as HTMLElement | null;
  const sourcePre = block.querySelector("pre.mermaid-source") as HTMLElement | null;
  if (viewport) viewport.hidden = next === "source";
  if (sourcePre) {
    sourcePre.hidden = next !== "source";
    sourcePre.classList.toggle("is-visible", next === "source");
  }
  block.querySelectorAll(".mermaid-mode-btn").forEach((btn) => {
    const isView = btn.getAttribute("data-mermaid-action") === "mode-view";
    const isSource = btn.getAttribute("data-mermaid-action") === "mode-source";
    btn.classList.toggle(
      "is-active",
      (next === "view" && isView) || (next === "source" && isSource)
    );
  });
}

async function copyMermaidSource(block: HTMLElement) {
  const source =
    block.dataset.mermaidSource || block.querySelector("pre.mermaid-source")?.textContent || "";
  const text = "```mermaid\n" + source.trim() + "\n```";
  try {
    await navigator.clipboard.writeText(text);
    setMermaidStatus(block, "已复制", false);
    setTimeout(() => {
      if (block.getAttribute("data-processed") === "ok") setMermaidStatus(block, "");
      else if (block.dataset.mermaidError) {
        setMermaidStatus(
          block,
          shortMermaidError(block.dataset.mermaidError),
          true,
          block.dataset.mermaidError
        );
      }
    }, 1000);
  } catch (err) {
    setMermaidStatus(block, `复制失败：${formatMermaidError(err)}`, true);
  }
}

function prepareMermaidSvgClone(svg: SVGSVGElement) {
  const clone = svg.cloneNode(true) as SVGSVGElement;
  if (!clone.getAttribute("xmlns")) clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  if (!clone.getAttribute("xmlns:xlink")) {
    clone.setAttribute("xmlns:xlink", "http://www.w3.org/1999/xlink");
  }
  const vb = clone.viewBox?.baseVal;
  let w = parseFloat(clone.getAttribute("width") || "") || vb?.width || 0;
  let h = parseFloat(clone.getAttribute("height") || "") || vb?.height || 0;
  if ((!w || !h || /%/.test(String(clone.getAttribute("width") || ""))) && vb?.width && vb?.height) {
    w = vb.width;
    h = vb.height;
  }
  if (!w || !h) {
    try {
      const b = svg.getBBox();
      if (b.width > 0 && b.height > 0) {
        w = b.width;
        h = b.height;
        if (!clone.getAttribute("viewBox")) {
          clone.setAttribute("viewBox", `${b.x} ${b.y} ${b.width} ${b.height}`);
        }
      }
    } catch {
      /* ignore */
    }
  }
  if (!w) w = 800;
  if (!h) h = 600;
  clone.setAttribute("width", String(w));
  clone.setAttribute("height", String(h));
  const bg = document.createElementNS("http://www.w3.org/2000/svg", "rect");
  bg.setAttribute("x", "0");
  bg.setAttribute("y", "0");
  bg.setAttribute("width", "100%");
  bg.setAttribute("height", "100%");
  bg.setAttribute("fill", diagramPanelBg());
  clone.insertBefore(bg, clone.firstChild);
  return { clone, w, h };
}

function triggerBlobDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1500);
}

async function downloadMermaidImage(block: HTMLElement, format: "svg" | "png" = "svg") {
  const svg = block.querySelector(".mermaid-stage svg") as SVGSVGElement | null;
  if (!svg) {
    setMermaidStatus(block, "暂无可下载的图", true);
    return;
  }
  try {
    const { clone, w, h } = prepareMermaidSvgClone(svg);
    // Strip foreignObject so canvas rasterization is not tainted.
    clone.querySelectorAll("foreignObject").forEach((fo) => {
      const text = (fo.textContent || "").trim();
      const x = fo.getAttribute("x") || "0";
      const y = fo.getAttribute("y") || "0";
      const tw = fo.getAttribute("width") || "80";
      const replacement = document.createElementNS("http://www.w3.org/2000/svg", "text");
      replacement.setAttribute("x", String(Number(x) + Number(tw) / 2));
      replacement.setAttribute("y", String(Number(y) + 14));
      replacement.setAttribute("text-anchor", "middle");
      replacement.setAttribute("fill", diagramInk());
      replacement.setAttribute("font-size", "12");
      replacement.setAttribute("font-family", "sans-serif");
      replacement.textContent = text.slice(0, 80);
      fo.replaceWith(replacement);
    });
    let xml = new XMLSerializer().serializeToString(clone);
    if (!xml.includes("xmlns=")) {
      xml = xml.replace("<svg", '<svg xmlns="http://www.w3.org/2000/svg"');
    }
    if (format === "svg") {
      const svgBlob = new Blob([xml], { type: "image/svg+xml;charset=utf-8" });
      triggerBlobDownload(svgBlob, `mermaid-${Date.now()}.svg`);
      setMermaidStatus(block, "已下载 SVG", false);
    } else {
      const svgBlob = new Blob([xml], { type: "image/svg+xml;charset=utf-8" });
      const url = URL.createObjectURL(svgBlob);
      try {
        const img = await new Promise<HTMLImageElement>((resolve, reject) => {
          const el = new Image();
          el.onload = () => resolve(el);
          el.onerror = () => reject(new Error("SVG rasterize failed"));
          el.src = url;
        });
        const scale = 2;
        const canvas = document.createElement("canvas");
        canvas.width = Math.max(1, Math.ceil((w || img.width || 800) * scale));
        canvas.height = Math.max(1, Math.ceil((h || img.height || 600) * scale));
        const ctx = canvas.getContext("2d")!;
        ctx.fillStyle = diagramPanelBg();
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        const pngBlob = await new Promise<Blob>((resolve, reject) => {
          canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("PNG encode failed"))), "image/png");
        });
        triggerBlobDownload(pngBlob, `mermaid-${Date.now()}.png`);
        setMermaidStatus(block, "已下载 PNG", false);
      } finally {
        URL.revokeObjectURL(url);
      }
    }
    setTimeout(() => {
      if (block.getAttribute("data-processed") === "ok") setMermaidStatus(block, "");
    }, 1200);
  } catch (err) {
    setMermaidStatus(block, `下载失败：${formatMermaidError(err)}`, true);
  }
}

function bindMermaidControls(root: any) {
  if (!root || root._nlmMermaidControls) return;
  root._nlmMermaidControls = true;
  root.addEventListener("click", async (ev: MouseEvent) => {
    const target = ev.target as HTMLElement;
    const zoomBtn = target?.closest?.("[data-mermaid-zoom]");
    const actionBtn = target?.closest?.("[data-mermaid-action]");
    const block = (zoomBtn || actionBtn)?.closest?.(".mermaid-block") as any;
    if (!block || !root.contains(block)) return;

    if (zoomBtn) {
      const action = zoomBtn.getAttribute("data-mermaid-zoom");
      const cur = Number(block.dataset.zoom) || 1;
      if (action === "in") applyMermaidZoom(block, cur + 0.15);
      else if (action === "out") applyMermaidZoom(block, cur - 0.15);
      return;
    }

    const action = actionBtn?.getAttribute("data-mermaid-action");
    if (action === "fold") {
      applyMermaidCollapsed(block, block.dataset.collapsed !== "1");
      return;
    }
    if (action === "mode-source") {
      if (block.dataset.collapsed === "1") applyMermaidCollapsed(block, false);
      applyMermaidMode(block, "source");
      return;
    }
    if (action === "mode-view") {
      if (block.dataset.collapsed === "1") applyMermaidCollapsed(block, false);
      applyMermaidMode(block, "view");
      if (!block.querySelector(".mermaid-stage svg") && typeof block._nlmRetry === "function") {
        await block._nlmRetry();
      }
      return;
    }
    if (action === "retry") {
      if (block.dataset.collapsed === "1") applyMermaidCollapsed(block, false);
      applyMermaidMode(block, "view");
      if (typeof block._nlmRetry === "function") await block._nlmRetry();
      return;
    }
    if (action === "copy") copyMermaidSource(block);
    else if (action === "download" || action === "download-svg") downloadMermaidImage(block, "svg");
    else if (action === "download-png") downloadMermaidImage(block, "png");
    else if (action === "fullscreen") openMermaidFullscreen(block);
  });
}

/** Wrap fenced code blocks with copy + fold chrome. */
export function enhanceCodeBlocks(root: any) {
  if (!root) return;
  if (!root._nlmCodeControls) {
    root._nlmCodeControls = true;
    root.addEventListener("click", async (ev: MouseEvent) => {
      const btn = (ev.target as HTMLElement)?.closest?.(
        "[data-code-action]",
      ) as HTMLElement | null;
      if (!btn || !root.contains(btn)) return;
      const wrap = btn.closest(".code-block") as HTMLElement | null;
      if (!wrap) return;
      const action = btn.getAttribute("data-code-action");
      if (action === "fold") {
        const next = wrap.dataset.collapsed !== "1";
        wrap.dataset.collapsed = next ? "1" : "0";
        wrap.classList.toggle("is-collapsed", next);
        btn.title = next ? "展开" : "折叠";
        btn.setAttribute("aria-expanded", next ? "false" : "true");
        return;
      }
      if (action === "copy") {
        const pre = wrap.querySelector("pre");
        const text = (pre as any)?.innerText || pre?.textContent || "";
        try {
          await navigator.clipboard.writeText(text);
          btn.classList.add("is-ok");
          setTimeout(() => btn.classList.remove("is-ok"), 900);
        } catch {
          btn.classList.add("is-err");
          setTimeout(() => btn.classList.remove("is-err"), 900);
        }
      }
    });
  }

  root.querySelectorAll("pre > code").forEach((codeEl: Element) => {
    const pre = codeEl.parentElement;
    if (
      !pre ||
      pre.closest(".mermaid-block") ||
      pre.closest(".echarts-block") ||
      pre.closest(".drawio-block") ||
      pre.closest(".code-block")
    ) {
      return;
    }
    if (
      pre.classList.contains("mermaid") ||
      pre.classList.contains("mermaid-source") ||
      pre.classList.contains("echarts-source")
    ) {
      return;
    }

    const wrap = document.createElement("div");
    wrap.className = "code-block";
    wrap.dataset.collapsed = "0";
    const lang =
      [...codeEl.classList]
        .map((c) => (c.startsWith("language-") ? c.slice("language-".length) : ""))
        .find(Boolean) || "";
    if (lang) wrap.dataset.lang = lang;

    const bar = document.createElement("div");
    bar.className = "code-toolbar";
    bar.innerHTML = `
      <button type="button" class="code-tool-btn icon-btn" data-code-action="fold" title="折叠" aria-label="折叠" aria-expanded="true">${iconSvg("fold")}</button>
      <span class="code-lang">${escapeHtml(lang || "code")}</span>
      <span class="code-toolbar-spacer"></span>
      <button type="button" class="code-tool-btn icon-btn" data-code-action="copy" title="复制代码" aria-label="复制">${iconSvg("copy")}</button>
    `;
    pre.parentNode!.insertBefore(wrap, pre);
    wrap.appendChild(bar);
    wrap.appendChild(pre);
  });
}

/** Status lives in the toolbar row. */
function setMermaidStatus(block: HTMLElement, text: string, isError = false, fullText = "") {
  let el = block.querySelector(".mermaid-status-inline") as HTMLElement | null;
  if (!el) {
    ensureMermaidChrome(block, block.dataset.mermaidSource || "");
    el = block.querySelector(".mermaid-status-inline") as HTMLElement | null;
  }
  block.querySelectorAll(".mermaid-status").forEach((n) => n.remove());
  if (!el) return;
  if (!text) {
    el.hidden = true;
    el.textContent = "";
    el.removeAttribute("title");
    el.classList.remove("is-error");
    return;
  }
  el.hidden = false;
  el.textContent = text;
  el.title = fullText || text;
  el.classList.toggle("is-error", !!isError);
}

async function renderOneMermaid(mermaid: any, block: HTMLElement, source: string) {
  const stage = ensureMermaidChrome(block, source);
  if (!stage) return;
  setMermaidStatus(block, "渲染中…");
  const id = `nlm-mmd-${Date.now()}-${++mermaidRenderSeq}`;
  try {
    const result = await mermaid.render(id, source);
    const svg = typeof result === "string" ? result : result?.svg;
    if (!svg) throw new Error("mermaid.render 未返回 SVG");
    if (isMermaidErrorSvg(svg)) {
      throw new Error("Syntax error in text (mermaid error diagram)");
    }
    stage.innerHTML = svg;
    if (typeof result?.bindFunctions === "function") result.bindFunctions(stage);
    delete block.dataset.mermaidError;
    setMermaidStatus(block, "");
    block.setAttribute("data-processed", "ok");
    applyMermaidMode(block, "view");
  } finally {
    cleanupMermaidArtifacts(id);
  }
}

export { renderDrawioIn };

export async function renderMermaidIn(
  root: HTMLElement | null,
  {
    streaming = false,
    repair = null,
    onFixed = null,
  }: {
    streaming?: boolean;
    repair?: ((source: string, error: string) => Promise<string>) | null;
    onFixed?: ((args: { from: string; to: string }) => void) | null;
  } = {}
) {
  if (!root) return;
  bindMermaidControls(root);

  const blocks = [...root.querySelectorAll(".mermaid-block")] as any[];
  if (!blocks.length) return;

  // During streaming, never call Mermaid — incomplete fences flood error SVGs.
  if (streaming) {
    for (const block of blocks) {
      if (block.getAttribute("data-processed") === "ok") continue;
      const pre = block.querySelector("pre.mermaid, pre.mermaid-source");
      const original = sanitizeMermaidSource(
        block.dataset.mermaidSource || pre?.textContent || ""
      );
      if (!original) continue;
      ensureMermaidChrome(block, original);
      const stage = block.querySelector(".mermaid-stage");
      if (stage) stage.innerHTML = "";
      applyMermaidMode(block, "source");
      setMermaidStatus(block, "生成中…");
      block.setAttribute("data-processed", "pending");
    }
    return;
  }

  const mermaid = await ensureMermaid();

  for (const block of blocks) {
    if (block.getAttribute("data-processed") === "ok" && block.querySelector(".mermaid-stage svg")) {
      const svgEl = block.querySelector(".mermaid-stage svg");
      if (svgEl && !isMermaidErrorSvg(svgEl.outerHTML)) continue;
      block.removeAttribute("data-processed");
    }

    const pre = block.querySelector("pre.mermaid, pre.mermaid-source");
    const original = sanitizeMermaidSource(
      block.dataset.mermaidSource || pre?.textContent || ""
    );
    if (!original) continue;

    const attemptRender = async (src: string, { allowRepair = true }: { allowRepair?: boolean } = {}) => {
      let source = src;
      let lastErr: any = null;
      let parsed: { ok: boolean; error: any } = { ok: false, error: null };

      try {
        await renderOneMermaid(mermaid, block, source);
        return true;
      } catch (err) {
        lastErr = err;
      }

      const cleaned = sanitizeMermaidSource(source);
      if (cleaned && cleaned !== source) {
        try {
          await renderOneMermaid(mermaid, block, cleaned);
          if (cleaned !== original && typeof onFixed === "function") {
            onFixed({ from: original, to: cleaned });
          }
          return true;
        } catch (err) {
          lastErr = err;
          source = cleaned;
        }
      }

      parsed = await tryParse(mermaid, source);
      if (parsed.ok) {
        try {
          await renderOneMermaid(mermaid, block, source);
          return true;
        } catch (err) {
          lastErr = err;
        }
      } else if (parsed.error) {
        lastErr = parsed.error;
      }

      // Any display failure → LLM regenerate (not only parse failures)
      if (allowRepair && typeof repair === "function") {
        const reason = formatMermaidError(lastErr);
        setMermaidStatus(block, `渲染失败，正在重新生成…`, true, reason);
        try {
          const fixedRaw = await repair(source, reason);
          const fixed = extractMermaidSource(fixedRaw || "");
          if (fixed) {
            await renderOneMermaid(mermaid, block, fixed);
            if (fixed !== original && typeof onFixed === "function") {
              onFixed({ from: original, to: fixed });
            }
            return true;
          }
          lastErr = new Error(`修复未返回可用源码（原错误：${reason}）`);
        } catch (err) {
          lastErr = new Error(`修复失败：${formatMermaidError(err)}｜原错误：${reason}`);
        }
      }

      ensureMermaidChrome(block, source);
      const stage = block.querySelector(".mermaid-stage");
      if (stage) stage.innerHTML = "";
      applyMermaidMode(block, "source");
      const full = formatMermaidError(lastErr);
      block.dataset.mermaidError = full;
      const prefix = parsed.ok ? "渲染失败" : "解析错误";
      setMermaidStatus(block, `${prefix}：${shortMermaidError(full, 64)}`, true, full);
      block.setAttribute("data-processed", parsed.ok ? "soft-fail" : "error");
      return false;
    };

    block._nlmRetry = async () => {
      block.removeAttribute("data-processed");
      delete block.dataset.mermaidError;
      setMermaidStatus(block, "重试中…");
      await attemptRender(block.dataset.mermaidSource || original, { allowRepair: true });
    };

    await attemptRender(original, { allowRepair: true });
  }
}

/**
 * DOM enhancement pass used by MarkdownBody after setting innerHTML.
 * Mirrors the Vue paint() sequence (links, code chrome, images).
 */
export function enhanceMarkdownRoot(root: HTMLElement | null) {
  if (!root) return;
  decorateMarkdownLinks(root);
  enhanceCodeBlocks(root);
  enhanceChatImages(root);
}
