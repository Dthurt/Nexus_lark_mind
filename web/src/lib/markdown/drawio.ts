/**
 * Draw.io / diagrams.net XML rendering via embed.diagrams.net (postMessage load).
 * Fence languages: drawio | diagrams | mxfile
 */

function escapeHtml(s: string) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
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
  if (name === "fold") {
    return `<svg ${common} class="icon-chevron"><polyline points="6 9 12 15 18 9"/></svg>`;
  }
  if (name === "external") {
    return `<svg ${common}><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>`;
  }
  return "";
}

const DRAWIO_LANGS = new Set(["drawio", "diagrams", "diagrams.net", "mxfile"]);

export function isDrawioLang(lang: string) {
  return DRAWIO_LANGS.has(String(lang || "").toLowerCase());
}

export function looksLikeDrawioXml(text: string) {
  const t = String(text || "").trim();
  return /<(mxfile|mxGraphModel)\b/i.test(t);
}

/** Normalize fence body into mxfile XML when possible. */
export function normalizeDrawioXml(raw: string) {
  let s = String(raw || "").trim();
  s = s.replace(/^```(?:drawio|diagrams|mxfile|xml)\s*/i, "").replace(/```\s*$/i, "").trim();
  if (!s) return "";
  if (/^<mxfile\b/i.test(s)) return s;
  if (/^<mxGraphModel\b/i.test(s)) {
    return `<mxfile host="app.diagrams.net"><diagram name="Page-1">${s}</diagram></mxfile>`;
  }
  return s;
}

export function drawioMarkdownHtml(text: string) {
  return `<div class="drawio-block" data-drawio-host="1"><pre class="drawio-source">${escapeHtml(text)}</pre></div>`;
}

/** Fast tier: keep source, do not mount viewer. */
export function drawioBlockedMarkdownHtml(text: string) {
  return `<div class="drawio-block drawio-blocked" data-drawio-host="1" data-drawio-blocked="1" data-processed="blocked"><div class="drawio-blocked-banner">Fast 体验档仅支持 Mermaid — Draw.io 已降级为源码</div><pre class="drawio-source is-visible">${escapeHtml(text)}</pre></div>`;
}

/** Prefer local viewer under /drawio/, else offline SVG preview, else remote embed. */
function resolveEmbedUrl(): string | null {
  try {
    const custom = localStorage.getItem("nlm_drawio_embed");
    if (custom) return custom;
  } catch {
    /* ignore */
  }
  // Same-origin bundled viewer (drop diagrams.net export into web/public/drawio/)
  return "/drawio/index.html?embed=1&proto=json&spin=1&ui=min&libraries=1&nav=1&layers=1&saveAndExit=0&noSaveBtn=1&noExitBtn=1&toolbar=0";
}

const REMOTE_EMBED_URL =
  "https://embed.diagrams.net/?embed=1&proto=json&spin=1&ui=min&libraries=1&nav=1&layers=1&saveAndExit=0&noSaveBtn=1&noExitBtn=1&toolbar=0";

/** Parse mxGraph cells into a simple offline SVG (no network). */
export function mxfileToOfflineSvg(xml: string): string {
  const src = String(xml || "");
  const cells: Array<{ x: number; y: number; w: number; h: number; label: string }> = [];
  const re =
    /<mxCell\b[^>]*\bvalue="([^"]*)"[^>]*\bvertex="1"[^>]*>[\s\S]*?<mxGeometry\b([^/]*)\/>/gi;
  let m: RegExpExecArray | null;
  while ((m = re.exec(src)) && cells.length < 80) {
    const label = String(m[1] || "")
      .replace(/&lt;/g, "<")
      .replace(/&gt;/g, ">")
      .replace(/&#xa;/gi, " ")
      .replace(/<[^>]+>/g, "")
      .trim()
      .slice(0, 48);
    const geo = m[2] || "";
    const num = (k: string, d = 0) => {
      const hit = new RegExp(`\\b${k}="([\\d.]+)"`).exec(geo);
      return hit ? parseFloat(hit[1]) : d;
    };
    cells.push({
      x: num("x"),
      y: num("y"),
      w: Math.max(num("width", 80), 40),
      h: Math.max(num("height", 40), 24),
      label: label || "node",
    });
  }
  if (!cells.length) {
    return `<svg xmlns="http://www.w3.org/2000/svg" width="320" height="64" viewBox="0 0 320 64"><rect width="320" height="64" fill="#1a1f26" rx="8"/><text x="16" y="38" fill="#9aa4b2" font-size="13" font-family="ui-sans-serif,system-ui">Offline preview — open source or external editor</text></svg>`;
  }
  let maxX = 0;
  let maxY = 0;
  for (const c of cells) {
    maxX = Math.max(maxX, c.x + c.w);
    maxY = Math.max(maxY, c.y + c.h);
  }
  const W = Math.max(Math.ceil(maxX + 24), 200);
  const H = Math.max(Math.ceil(maxY + 24), 80);
  const rects = cells
    .map((c) => {
      const tx = escapeHtml(c.label);
      return `<rect x="${c.x}" y="${c.y}" width="${c.w}" height="${c.h}" rx="6" fill="#243041" stroke="#5b8def" stroke-width="1.2"/><text x="${c.x + c.w / 2}" y="${c.y + c.h / 2 + 4}" text-anchor="middle" fill="#e8eef7" font-size="11" font-family="ui-sans-serif,system-ui">${tx}</text>`;
    })
    .join("");
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" style="max-width:100%;height:auto;display:block;margin-inline:auto">${rects}</svg>`;
}

function setStatus(block: HTMLElement, text: string, isError = false) {
  const el = block.querySelector(".drawio-status-inline") as HTMLElement | null;
  if (!el) return;
  if (!text) {
    el.hidden = true;
    el.textContent = "";
    el.classList.remove("is-error");
    return;
  }
  el.hidden = false;
  el.textContent = text;
  el.title = text;
  el.classList.toggle("is-error", !!isError);
}

function ensureChrome(block: HTMLElement, xml: string) {
  block.dataset.drawioSource = xml;
  if (!block.querySelector(".drawio-toolbar")) {
    const bar = document.createElement("div");
    bar.className = "drawio-toolbar";
    bar.innerHTML = `
      <button type="button" class="mermaid-tool-btn icon-btn" data-drawio-action="fold" title="折叠/展开" aria-label="折叠">${iconSvg("fold")}</button>
      <span class="drawio-badge">Draw.io</span>
      <span class="drawio-status-inline" hidden></span>
      <span class="mermaid-toolbar-spacer"></span>
      <button type="button" class="mermaid-tool-btn icon-btn" data-drawio-action="copy" title="复制 XML" aria-label="复制">${iconSvg("copy")}</button>
      <button type="button" class="mermaid-tool-btn icon-btn" data-drawio-action="external" title="在 diagrams.net 打开" aria-label="外链">${iconSvg("external")}</button>
      <button type="button" class="mermaid-tool-btn icon-btn" data-drawio-action="fullscreen" title="全屏" aria-label="全屏">${iconSvg("fullscreen")}</button>
      <button type="button" class="mermaid-mode-btn is-active" data-drawio-action="mode-view">视图</button>
      <button type="button" class="mermaid-mode-btn" data-drawio-action="mode-source">源码</button>
    `;
    block.insertBefore(bar, block.firstChild);
  }
  if (!block.querySelector(".drawio-viewport")) {
    const viewport = document.createElement("div");
    viewport.className = "drawio-viewport";
    const offline = document.createElement("div");
    offline.className = "drawio-offline-host";
    viewport.appendChild(offline);
    const frame = document.createElement("iframe");
    frame.className = "drawio-frame";
    frame.title = "Draw.io diagram";
    frame.hidden = true;
    frame.setAttribute("referrerpolicy", "no-referrer");
    frame.setAttribute(
      "sandbox",
      "allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox"
    );
    viewport.appendChild(frame);
    block.appendChild(viewport);
  }
  const sourcePre = block.querySelector("pre.drawio-source") as HTMLElement | null;
  if (sourcePre) {
    sourcePre.textContent = xml;
    sourcePre.hidden = true;
    sourcePre.classList.remove("is-visible");
  }
  return block.querySelector(".drawio-frame") as HTMLIFrameElement;
}

function applyCollapsed(block: HTMLElement, collapsed: boolean) {
  block.dataset.collapsed = collapsed ? "1" : "0";
  block.classList.toggle("is-collapsed", !!collapsed);
  const vp = block.querySelector(".drawio-viewport") as HTMLElement | null;
  const src = block.querySelector("pre.drawio-source") as HTMLElement | null;
  if (collapsed) {
    if (vp) vp.hidden = true;
    if (src) {
      src.hidden = true;
      src.classList.remove("is-visible");
    }
  } else {
    applyMode(block, block.dataset.mode || "view");
  }
}

function applyMode(block: HTMLElement, mode: string) {
  if (block.dataset.collapsed === "1") return;
  const next = mode === "source" ? "source" : "view";
  block.dataset.mode = next;
  const vp = block.querySelector(".drawio-viewport") as HTMLElement | null;
  const src = block.querySelector("pre.drawio-source") as HTMLElement | null;
  if (vp) vp.hidden = next === "source";
  if (src) {
    src.hidden = next !== "source";
    src.classList.toggle("is-visible", next === "source");
  }
  block.querySelectorAll("[data-drawio-action^='mode-']").forEach((btn) => {
    const a = btn.getAttribute("data-drawio-action");
    btn.classList.toggle("is-active", a === `mode-${next}`);
  });
}

function postLoad(iframe: HTMLIFrameElement, xml: string) {
  try {
    iframe.contentWindow?.postMessage(JSON.stringify({ action: "load", xml }), "*");
  } catch {
    /* ignore */
  }
}

function mountFrame(
  block: HTMLElement,
  iframe: any,
  xml: string,
  {
    onError = null,
  }: { onError?: ((message: string) => void) | null } = {}
) {
  if (iframe._nlmDrawioCleanup) iframe._nlmDrawioCleanup();
  setStatus(block, "加载 Draw.io…");

  const onMessage = (ev: MessageEvent) => {
    if (ev.source !== iframe.contentWindow) return;
    let data: any = ev.data;
    if (typeof data === "string") {
      if (data === "ready") {
        postLoad(iframe, xml);
        return;
      }
      try {
        data = JSON.parse(data);
      } catch {
        return;
      }
    }
    if (!data || typeof data !== "object") return;
    if (data.event === "init") {
      postLoad(iframe, xml);
    } else if (data.event === "load" || data.event === "rendered") {
      setStatus(block, "");
      block.setAttribute("data-processed", "ok");
    } else if (data.event === "error") {
      const msg = data.message || "Draw.io 渲染失败";
      block.setAttribute("data-processed", "error");
      if (typeof onError === "function") onError(msg);
      else setStatus(block, msg, true);
    }
  };

  window.addEventListener("message", onMessage);
  iframe._nlmDrawioCleanup = () => window.removeEventListener("message", onMessage);

  iframe.onload = () => {
    setTimeout(() => postLoad(iframe, xml), 400);
  };
  const prefer = resolveEmbedUrl();
  iframe.src = prefer || REMOTE_EMBED_URL;
}

function mountOfflinePreview(block: HTMLElement, xml: string) {
  const iframe = ensureChrome(block, xml);
  iframe.hidden = true;
  const host = block.querySelector(".drawio-offline-host") as HTMLElement | null;
  if (host) {
    host.hidden = false;
    host.innerHTML = mxfileToOfflineSvg(xml);
  }
  setStatus(block, "离线预览");
  block.setAttribute("data-processed", "ok");
  block.dataset.drawioMode = "offline";
  applyMode(block, "view");
}

async function probeLocalEmbed(): Promise<boolean> {
  try {
    const url = resolveEmbedUrl();
    if (!url || url.startsWith("http")) return false;
    const res = await fetch(url.split("?")[0], { method: "HEAD", cache: "no-store" });
    return res.ok;
  } catch {
    return false;
  }
}

async function copyXml(block: HTMLElement) {
  const xml = block.dataset.drawioSource || block.querySelector("pre.drawio-source")?.textContent || "";
  const text = "```drawio\n" + xml.trim() + "\n```";
  try {
    await navigator.clipboard.writeText(text);
    setStatus(block, "已复制");
    setTimeout(() => {
      if (block.getAttribute("data-processed") === "ok") setStatus(block, "");
    }, 1000);
  } catch (err: any) {
    setStatus(block, `复制失败：${err?.message || err}`, true);
  }
}

function openExternal(xml: string) {
  // Hash #R with URI-encoded XML (works for modest sizes).
  const url = `https://app.diagrams.net/?splash=0&ui=dark#R${encodeURIComponent(xml)}`;
  window.open(url, "_blank", "noopener,noreferrer");
}

function closeDrawioFullscreen() {
  document.querySelectorAll(".drawio-fs-overlay").forEach((el: any) => {
    if (typeof el._nlmFsCleanup === "function") el._nlmFsCleanup();
    el.remove();
  });
  document.documentElement.classList.remove("mermaid-fs-open");
}

function openDrawioFullscreen(block: HTMLElement) {
  closeDrawioFullscreen();
  const xml = block.dataset.drawioSource || "";
  const overlay = document.createElement("div");
  overlay.className = "mermaid-fs-overlay drawio-fs-overlay";
  overlay.innerHTML = `
    <div class="mermaid-fs-panel" role="dialog" aria-modal="true" aria-label="Draw.io 全屏">
      <div class="mermaid-fs-toolbar">
        <span class="mermaid-fs-title">Draw.io</span>
        <div class="mermaid-fs-tools">
          <button type="button" class="mermaid-tool-btn" data-fs-close="1">关闭</button>
        </div>
      </div>
      <div class="drawio-fs-viewport"></div>
    </div>
  `;
  const host = overlay.querySelector(".drawio-fs-viewport")!;
  const frame = document.createElement("iframe");
  frame.className = "drawio-frame drawio-fs-frame";
  frame.title = "Draw.io fullscreen";
  frame.setAttribute("referrerpolicy", "no-referrer");
  frame.setAttribute(
    "sandbox",
    "allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox"
  );
  host.appendChild(frame);

  const onKey = (ev: KeyboardEvent) => {
    if (ev.key === "Escape") closeDrawioFullscreen();
  };
  overlay.addEventListener("click", (ev) => {
    if (ev.target === overlay || (ev.target as HTMLElement)?.closest?.("[data-fs-close]"))
      closeDrawioFullscreen();
  });
  document.addEventListener("keydown", onKey);
  (overlay as any)._nlmFsCleanup = () => document.removeEventListener("keydown", onKey);

  document.body.appendChild(overlay);
  document.documentElement.classList.add("mermaid-fs-open");
  mountFrame(overlay, frame, xml);
}

function bindControls(root: any) {
  if (!root || root._nlmDrawioControls) return;
  root._nlmDrawioControls = true;
  root.addEventListener("click", async (ev: MouseEvent) => {
    const btn = (ev.target as HTMLElement)?.closest?.("[data-drawio-action]");
    if (!btn || !root.contains(btn)) return;
    const block = btn.closest(".drawio-block") as HTMLElement | null;
    if (!block) return;
    const action = btn.getAttribute("data-drawio-action");
    if (action === "fold") {
      applyCollapsed(block, block.dataset.collapsed !== "1");
      return;
    }
    if (action === "mode-source") {
      if (block.dataset.collapsed === "1") applyCollapsed(block, false);
      applyMode(block, "source");
      return;
    }
    if (action === "mode-view") {
      if (block.dataset.collapsed === "1") applyCollapsed(block, false);
      applyMode(block, "view");
      return;
    }
    if (action === "copy") {
      await copyXml(block);
      return;
    }
    if (action === "external") {
      openExternal(block.dataset.drawioSource || "");
      return;
    }
    if (action === "fullscreen") openDrawioFullscreen(block);
  });
}

function extractDrawioSource(raw: string) {
  const text = String(raw || "").trim();
  if (!text) return "";
  const fenced = text.match(/```(?:drawio|diagrams|mxfile|xml)\s*([\s\S]*?)```/i);
  if (fenced) return normalizeDrawioXml(fenced[1]);
  return normalizeDrawioXml(text);
}

export async function renderDrawioIn(
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
  bindControls(root);
  if (streaming) return;

  const blocks = [...root.querySelectorAll(".drawio-block")] as any[];
  for (const block of blocks) {
    if (block.getAttribute("data-drawio-blocked") === "1") continue;
    if (
      block.getAttribute("data-processed") === "ok" &&
      (block.querySelector(".drawio-offline-host svg") ||
        (block.querySelector("iframe.drawio-frame") as HTMLIFrameElement)?.src)
    ) {
      continue;
    }
    const pre = block.querySelector("pre.drawio-source");
    const original = block.dataset.drawioSource || pre?.textContent || "";

    const mountOk = async (xml: string) => {
      const iframe = ensureChrome(block, xml);
      applyMode(block, "view");
      const hasLocal = await probeLocalEmbed();
      if (!hasLocal) {
        mountOfflinePreview(block, xml);
        return;
      }
      iframe.hidden = false;
      const host = block.querySelector(".drawio-offline-host") as HTMLElement | null;
      if (host) host.hidden = true;
      mountFrame(block, iframe, xml, {
        onError: (msg) => {
          void (async () => {
            // Fall back to offline SVG if iframe embed fails
            mountOfflinePreview(block, xml);
            if (block._nlmDrawioRepaired || typeof repair !== "function") {
              setStatus(block, `${msg} · 已用离线预览`, true);
              return;
            }
            block._nlmDrawioRepaired = true;
            setStatus(block, "渲染失败，正在重新生成…", true);
            try {
              const fixedRaw = await repair(xml, msg);
              const fixed = extractDrawioSource(fixedRaw || "");
              if (!fixed || !looksLikeDrawioXml(fixed)) {
                setStatus(block, msg, true);
                return;
              }
              if (fixed !== original && typeof onFixed === "function") {
                onFixed({ from: original, to: fixed });
              }
              mountOfflinePreview(block, fixed);
            } catch (err: any) {
              setStatus(block, `修复失败：${err?.message || err}`, true);
              applyMode(block, "source");
            }
          })();
        },
      });
    };

    let xml = normalizeDrawioXml(original);
    if (!xml || !looksLikeDrawioXml(xml)) {
      if (typeof repair === "function") {
        setStatus(block, "XML 无效，正在重新生成…", true);
        ensureChrome(block, original);
        applyMode(block, "source");
        try {
          const fixedRaw = await repair(original || xml, "不是有效的 Draw.io / mxfile XML");
          const fixed = extractDrawioSource(fixedRaw || "");
          if (fixed && looksLikeDrawioXml(fixed)) {
            if (fixed !== original && typeof onFixed === "function") {
              onFixed({ from: original, to: fixed });
            }
            block._nlmDrawioRepaired = true;
            mountOk(fixed);
            continue;
          }
        } catch (err: any) {
          setStatus(block, `修复失败：${err?.message || err}`, true);
          block.setAttribute("data-processed", "error");
          continue;
        }
      }
      ensureChrome(block, xml || original);
      setStatus(block, "不是有效的 Draw.io / mxfile XML", true);
      applyMode(block, "source");
      block.setAttribute("data-processed", "error");
      continue;
    }
    await mountOk(xml);
  }
}
