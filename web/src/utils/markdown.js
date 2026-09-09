import { marked } from "marked";
import DOMPurify from "dompurify";
import { openMermaidFullscreen } from "./mermaidFullscreen.js";
import { drawioMarkdownHtml, isDrawioLang, looksLikeDrawioXml, renderDrawioIn } from "./drawio.js";

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

const renderer = new marked.Renderer();
const baseCode =
  typeof renderer.code === "function"
    ? renderer.code.bind(renderer)
    : null;

renderer.code = function codeToken(token, infoOrLang, escaped) {
  let text;
  let lang;
  if (token && typeof token === "object" && "text" in token) {
    text = token.text || "";
    lang = (token.lang || "").trim().split(/\s+/)[0] || "";
  } else {
    text = String(token || "");
    lang = String(infoOrLang || "")
      .trim()
      .split(/\s+/)[0] || "";
  }
  const langKey = lang.toLowerCase();
  if (langKey === "mermaid") {
    return `<div class="mermaid-block" data-mermaid-host="1"><pre class="mermaid">${escapeHtml(text)}</pre></div>`;
  }
  if (isDrawioLang(langKey) || (langKey === "xml" && looksLikeDrawioXml(text))) {
    return drawioMarkdownHtml(text);
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
  headerIds: false,
  mangle: false,
  renderer,
});

export function renderMarkdown(text, { streaming = false } = {}) {
  const raw = text || "";
  let html = marked.parse(raw);
  html = DOMPurify.sanitize(html, {
    USE_PROFILES: { html: true },
    ADD_ATTR: [
      "target",
      "rel",
      "class",
      "data-mermaid-host",
      "data-mermaid-zoom",
      "data-mermaid-action",
      "data-drawio-host",
      "data-drawio-action",
      "data-code-action",
      "data-mode",
      "data-lang",
      "data-collapsed",
      "title",
      "aria-label",
      "aria-expanded",
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
    ],
    ADD_TAGS: ["div", "button", "span", "pre", "svg", "path", "rect", "polyline", "line"],
  });
  if (streaming) html += '<span class="streaming-caret" aria-hidden="true"></span>';
  return html;
}

export function decorateMarkdownLinks(root) {
  if (!root) return;
  root.querySelectorAll("a[href]").forEach((a) => {
    a.target = "_blank";
    a.rel = "noopener noreferrer";
  });
}

let mermaidReady = null;
let mermaidRenderSeq = 0;

async function ensureMermaid() {
  if (!mermaidReady) {
    mermaidReady = import("mermaid").then((mod) => {
      const mermaid = mod.default || mod;
      mermaid.initialize({
        startOnLoad: false,
        theme: "dark",
        securityLevel: "loose",
        fontFamily: "IBM Plex Sans, PingFang SC, Microsoft YaHei, sans-serif",
        flowchart: { htmlLabels: true, curve: "basis" },
      });
      return mermaid;
    });
  }
  return mermaidReady;
}

function decodeEntities(s) {
  return String(s || "")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&amp;/g, "&")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'");
}

/** Fix common model Mermaid typos without breaking valid arrows like `-.->`. */
export function sanitizeMermaidSource(raw) {
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

export function extractMermaidSource(text) {
  const raw = String(text || "").trim();
  const fenced = raw.match(/```mermaid\s*([\s\S]*?)```/i);
  if (fenced) return sanitizeMermaidSource(fenced[1]);
  return sanitizeMermaidSource(raw);
}

function formatMermaidError(err) {
  if (err == null || err === "") return "未知错误";
  if (typeof err === "string") return err.trim();
  const parts = [];
  if (err.str) parts.push(String(err.str));
  if (err.message) parts.push(String(err.message));
  if (err.hash?.text) parts.push(String(err.hash.text));
  if (err.hash?.token) parts.push(`token: ${err.hash.token}`);
  if (err.hash?.line != null) parts.push(`line ${err.hash.line}`);
  if (err.cause) parts.push(formatMermaidError(err.cause));
  const joined = parts.filter(Boolean).join(" · ");
  return (joined || String(err)).replace(/\s+/g, " ").trim();
}

function shortMermaidError(err, max = 72) {
  const full = typeof err === "string" ? err : formatMermaidError(err);
  if (full.length <= max) return full;
  return `${full.slice(0, max - 1)}…`;
}

async function tryParse(mermaid, source) {
  if (typeof mermaid.parse !== "function") return { ok: true, error: null };
  try {
    const ret = mermaid.parse(source);
    if (ret && typeof ret.then === "function") await ret;
    return { ok: true, error: null };
  } catch (err) {
    return { ok: false, error: err };
  }
}

function iconSvg(name) {
  const common = 'width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"';
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

function ensureMermaidChrome(block, source) {
  block.dataset.mermaidSource = source;
  if (!block.querySelector(".mermaid-toolbar")) {
    const bar = document.createElement("div");
    bar.className = "mermaid-toolbar";
    bar.innerHTML = `
      <button type="button" class="mermaid-tool-btn icon-btn" data-mermaid-action="fold" title="折叠/展开" aria-label="折叠">${iconSvg("fold")}</button>
      <span class="mermaid-status-inline" hidden></span>
      <span class="mermaid-toolbar-spacer"></span>
      <button type="button" class="mermaid-tool-btn icon-btn" data-mermaid-action="copy" title="复制源码" aria-label="复制">${iconSvg("copy")}</button>
      <button type="button" class="mermaid-tool-btn icon-btn" data-mermaid-action="download" title="下载图片 (SVG)" aria-label="下载">${iconSvg("download")}</button>
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
    const pre = block.querySelector("pre.mermaid");
    if (pre) {
      pre.classList.add("mermaid-source");
      pre.hidden = true;
      block.appendChild(pre);
    }
    viewport.appendChild(stage);
    block.appendChild(viewport);
  } else if (!block.querySelector(".mermaid-stage")) {
    const viewport = block.querySelector(".mermaid-viewport");
    const stage = document.createElement("div");
    stage.className = "mermaid-stage";
    const pre = viewport.querySelector("pre.mermaid");
    if (pre) {
      pre.classList.add("mermaid-source");
      pre.hidden = true;
      block.appendChild(pre);
    }
    viewport.appendChild(stage);
  }
  let sourcePre = block.querySelector("pre.mermaid-source, pre.mermaid");
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
  return block.querySelector(".mermaid-stage");
}

function applyMermaidCollapsed(block, collapsed) {
  block.dataset.collapsed = collapsed ? "1" : "0";
  block.classList.toggle("is-collapsed", !!collapsed);
  const foldBtn = block.querySelector('[data-mermaid-action="fold"]');
  if (foldBtn) {
    foldBtn.title = collapsed ? "展开" : "折叠";
    foldBtn.setAttribute("aria-expanded", collapsed ? "false" : "true");
  }
  if (collapsed) {
    const viewport = block.querySelector(".mermaid-viewport");
    const sourcePre = block.querySelector("pre.mermaid-source");
    if (viewport) viewport.hidden = true;
    if (sourcePre) {
      sourcePre.hidden = true;
      sourcePre.classList.remove("is-visible");
    }
  } else {
    applyMermaidMode(block, block.dataset.mode || "view");
  }
}

function applyMermaidZoom(block, zoom) {
  const z = Math.min(3, Math.max(0.4, zoom));
  block.dataset.zoom = String(z);
  const stage = block.querySelector(".mermaid-stage");
  if (stage) {
    stage.style.transform = `scale(${z})`;
    stage.style.transformOrigin = "top center";
  }
}

function applyMermaidMode(block, mode) {
  if (block.dataset.collapsed === "1") return;
  const next = mode === "source" ? "source" : "view";
  block.dataset.mode = next;
  const viewport = block.querySelector(".mermaid-viewport");
  const sourcePre = block.querySelector("pre.mermaid-source");
  if (viewport) viewport.hidden = next === "source";
  if (sourcePre) {
    sourcePre.hidden = next !== "source";
    sourcePre.classList.toggle("is-visible", next === "source");
  }
  block.querySelectorAll(".mermaid-mode-btn").forEach((btn) => {
    const isView = btn.getAttribute("data-mermaid-action") === "mode-view";
    const isSource = btn.getAttribute("data-mermaid-action") === "mode-source";
    btn.classList.toggle("is-active", (next === "view" && isView) || (next === "source" && isSource));
  });
}

async function copyMermaidSource(block) {
  const source = block.dataset.mermaidSource || block.querySelector("pre.mermaid-source")?.textContent || "";
  const text = "```mermaid\n" + source.trim() + "\n```";
  try {
    await navigator.clipboard.writeText(text);
    setMermaidStatus(block, "已复制", false);
    setTimeout(() => {
      if (block.getAttribute("data-processed") === "ok") setMermaidStatus(block, "");
      else if (block.dataset.mermaidError) {
        setMermaidStatus(block, shortMermaidError(block.dataset.mermaidError), true, block.dataset.mermaidError);
      }
    }, 1000);
  } catch (err) {
    setMermaidStatus(block, `复制失败：${formatMermaidError(err)}`, true);
  }
}

function prepareMermaidSvgClone(svg) {
  const clone = svg.cloneNode(true);
  if (!clone.getAttribute("xmlns")) clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  if (!clone.getAttribute("xmlns:xlink")) {
    clone.setAttribute("xmlns:xlink", "http://www.w3.org/1999/xlink");
  }
  const vb = clone.viewBox?.baseVal;
  let w = parseFloat(clone.getAttribute("width")) || vb?.width || 0;
  let h = parseFloat(clone.getAttribute("height")) || vb?.height || 0;
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
  bg.setAttribute("fill", "#0d1520");
  clone.insertBefore(bg, clone.firstChild);
  return { clone, w, h };
}

function triggerBlobDownload(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1500);
}

async function downloadMermaidImage(block) {
  const svg = block.querySelector(".mermaid-stage svg");
  if (!svg) {
    setMermaidStatus(block, "暂无可下载的图", true);
    return;
  }
  try {
    // Mermaid uses <foreignObject> for labels; canvas PNG export taints in Chrome.
    // SVG keeps full fidelity and never hits that security restriction.
    const { clone } = prepareMermaidSvgClone(svg);
    let xml = new XMLSerializer().serializeToString(clone);
    if (!xml.includes("xmlns=")) {
      xml = xml.replace("<svg", '<svg xmlns="http://www.w3.org/2000/svg"');
    }
    const svgBlob = new Blob([xml], { type: "image/svg+xml;charset=utf-8" });
    triggerBlobDownload(svgBlob, `mermaid-${Date.now()}.svg`);
    setMermaidStatus(block, "已下载", false);
    setTimeout(() => {
      if (block.getAttribute("data-processed") === "ok") setMermaidStatus(block, "");
    }, 1200);
  } catch (err) {
    setMermaidStatus(block, `下载失败：${formatMermaidError(err)}`, true);
  }
}

function bindMermaidControls(root) {
  if (!root || root._nlmMermaidControls) return;
  root._nlmMermaidControls = true;
  root.addEventListener("click", async (ev) => {
    const zoomBtn = ev.target?.closest?.("[data-mermaid-zoom]");
    const actionBtn = ev.target?.closest?.("[data-mermaid-action]");
    const block = (zoomBtn || actionBtn)?.closest?.(".mermaid-block");
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
    else if (action === "download") downloadMermaidImage(block);
    else if (action === "fullscreen") openMermaidFullscreen(block);
  });
}

/** Wrap fenced code blocks with copy + fold chrome. */
export function enhanceCodeBlocks(root) {
  if (!root) return;
  if (!root._nlmCodeControls) {
    root._nlmCodeControls = true;
    root.addEventListener("click", async (ev) => {
      const btn = ev.target?.closest?.("[data-code-action]");
      if (!btn || !root.contains(btn)) return;
      const wrap = btn.closest(".code-block");
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
        const text = pre?.innerText || pre?.textContent || "";
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

  root.querySelectorAll("pre > code").forEach((codeEl) => {
    const pre = codeEl.parentElement;
    if (!pre || pre.closest(".mermaid-block") || pre.closest(".code-block")) return;
    if (pre.classList.contains("mermaid") || pre.classList.contains("mermaid-source")) return;

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
    pre.parentNode.insertBefore(wrap, pre);
    wrap.appendChild(bar);
    wrap.appendChild(pre);
  });
}

/** Status lives in the toolbar row. */
function setMermaidStatus(block, text, isError = false, fullText = "") {
  let el = block.querySelector(".mermaid-status-inline");
  if (!el) {
    ensureMermaidChrome(block, block.dataset.mermaidSource || "");
    el = block.querySelector(".mermaid-status-inline");
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

async function renderOneMermaid(mermaid, block, source) {
  const stage = ensureMermaidChrome(block, source);
  if (!stage) return;
  setMermaidStatus(block, "渲染中…");
  const id = `nlm-mmd-${Date.now()}-${++mermaidRenderSeq}`;
  const result = await mermaid.render(id, source);
  const svg = typeof result === "string" ? result : result?.svg;
  if (!svg) throw new Error("mermaid.render 未返回 SVG");
  stage.innerHTML = svg;
  if (typeof result?.bindFunctions === "function") result.bindFunctions(stage);
  delete block.dataset.mermaidError;
  setMermaidStatus(block, "");
  block.setAttribute("data-processed", "ok");
  applyMermaidMode(block, "view");
}

export { renderDrawioIn };

export async function renderMermaidIn(
  root,
  { streaming = false, repair = null, onFixed = null } = {}
) {
  if (!root) return;
  bindMermaidControls(root);
  if (streaming) return;

  const blocks = [...root.querySelectorAll(".mermaid-block")];
  if (!blocks.length) return;

  const mermaid = await ensureMermaid();

  for (const block of blocks) {
    if (block.getAttribute("data-processed") === "ok" && block.querySelector(".mermaid-stage svg")) {
      continue;
    }

    const pre = block.querySelector("pre.mermaid, pre.mermaid-source");
    const original = sanitizeMermaidSource(
      block.dataset.mermaidSource || pre?.textContent || ""
    );
    if (!original) continue;

    const attemptRender = async (src, { allowRepair = true } = {}) => {
      let source = src;
      let lastErr = null;
      let parsed = { ok: false, error: null };

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

      if (allowRepair && !parsed.ok && typeof repair === "function") {
        const reason = formatMermaidError(lastErr);
        setMermaidStatus(block, `语法错误，正在重新生成…`, true, reason);
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
      await attemptRender(block.dataset.mermaidSource || original, { allowRepair: false });
    };

    await attemptRender(original, { allowRepair: true });
  }
}
