/** ECharts fenced blocks — ```echarts / ```echart JSON option. */

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function iconSvg(name) {
  const common =
    'width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"';
  if (name === "fold") {
    return `<svg class="icon-chevron" ${common}><polyline points="6 9 12 15 18 9"/></svg>`;
  }
  if (name === "copy") {
    return `<svg ${common}><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/></svg>`;
  }
  if (name === "download") {
    return `<svg ${common}><path d="M12 3v12"/><path d="M7 10l5 5 5-5"/><path d="M5 21h14"/></svg>`;
  }
  if (name === "fullscreen") {
    return `<svg ${common}><path d="M8 3H5a2 2 0 0 0-2 2v3"/><path d="M16 3h3a2 2 0 0 1 2 2v3"/><path d="M8 21H5a2 2 0 0 1-2-2v-3"/><path d="M16 21h3a2 2 0 0 0 2-2v-3"/></svg>`;
  }
  if (name === "minus") {
    return `<svg ${common}><line x1="5" y1="12" x2="19" y2="12"/></svg>`;
  }
  if (name === "plus") {
    return `<svg ${common}><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>`;
  }
  if (name === "retry") {
    return `<svg ${common}><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/></svg>`;
  }
  return "";
}

export function isEchartsLang(lang) {
  const k = String(lang || "").toLowerCase();
  return k === "echarts" || k === "echart" || k === "echarts-json";
}

/** Heuristic: JSON that looks like an ECharts option object. */
export function looksLikeEchartsOption(text) {
  const s = String(text || "").trim();
  if (!s.startsWith("{") || s.length < 24) return false;
  const hasSeries = /"series"\s*:/.test(s);
  const hasAxis = /"(xAxis|yAxis|radar|geo|angleAxis|radiusAxis)"\s*:/.test(s);
  const hasChartType =
    /"type"\s*:\s*"(line|bar|pie|scatter|radar|heatmap|funnel|gauge|candlestick|boxplot)"/.test(s);
  return hasSeries && (hasAxis || hasChartType);
}

export function echartsMarkdownHtml(source) {
  return `<div class="echarts-block" data-echarts-host="1"><pre class="echarts-source">${escapeHtml(source)}</pre></div>`;
}

function extractBalancedObject(src, from) {
  if (src[from] !== "{") return null;
  let depth = 0;
  let inStr = false;
  let esc = false;
  for (let i = from; i < src.length; i += 1) {
    const ch = src[i];
    if (inStr) {
      if (esc) esc = false;
      else if (ch === "\\") esc = true;
      else if (ch === '"') inStr = false;
      continue;
    }
    if (ch === '"') {
      inStr = true;
      continue;
    }
    if (ch === "{") depth += 1;
    else if (ch === "}") {
      depth -= 1;
      if (depth === 0) return src.slice(from, i + 1);
    }
  }
  return null;
}

/**
 * Repair common model mistakes so charts still render:
 * - bare `echarts` + JSON (no fences)
 * - ```json containing an ECharts option
 */
export function normalizeEchartsMarkdown(raw) {
  let text = String(raw || "");
  if (!text) return text;

  // ```json / ```javascript with echarts-like body → ```echarts
  text = text.replace(/```(?:json|javascript|js)\s*\n([\s\S]*?)```/gi, (full, body) => {
    if (looksLikeEchartsOption(body)) {
      return `\`\`\`echarts\n${String(body).trim()}\n\`\`\``;
    }
    return full;
  });

  // Already properly fenced echarts — leave alone
  if (/```echarts?\b/i.test(text)) {
    // Still try to wrap remaining bare echarts blobs outside fences below
  }

  // Bare: ...echarts\n{ ... }
  const bareRe = /(^|[^`])echarts\s*\r?\n\s*\{/gi;
  let out = "";
  let last = 0;
  let m;
  while ((m = bareRe.exec(text)) !== null) {
    const braceAt = text.indexOf("{", m.index + m[0].length - 1);
    if (braceAt < 0) continue;
    // Skip if this sits inside an existing ``` fence
    const before = text.slice(0, m.index);
    const fenceOpen = (before.match(/```/g) || []).length;
    if (fenceOpen % 2 === 1) continue;

    const json = extractBalancedObject(text, braceAt);
    if (!json || !looksLikeEchartsOption(json)) continue;

    out += text.slice(last, m.index) + (m[1] || "");
    if (out.length && !/\n\s*$/.test(out)) out += "\n";
    out += `\`\`\`echarts\n${json.trim()}\n\`\`\``;
    last = braceAt + json.length;
    bareRe.lastIndex = last;
  }
  out += text.slice(last);
  text = out || text;

  return text;
}

let echartsMod = null;
async function ensureEcharts() {
  if (!echartsMod) {
    echartsMod = await import("echarts");
  }
  return echartsMod;
}

function parseOption(raw) {
  let text = String(raw || "").trim();
  if (!text) throw new Error("empty echarts option");
  text = text
    .replace(/^```(?:echarts|echart|echarts-json|json)?\s*/i, "")
    .replace(/```\s*$/i, "")
    .trim();
  const start = text.indexOf("{");
  const end = text.lastIndexOf("}");
  if (start >= 0 && end > start) text = text.slice(start, end + 1);
  // Tolerate trailing commas common in model output
  text = text.replace(/,\s*([}\]])/g, "$1");
  return JSON.parse(text);
}

function setStatus(block, text, isError = false) {
  let el = block.querySelector(".echarts-status-inline");
  if (!el) return;
  if (!text) {
    el.hidden = true;
    el.textContent = "";
    el.classList.remove("is-error");
    return;
  }
  el.hidden = false;
  el.textContent = text;
  el.classList.toggle("is-error", !!isError);
}

function ensureChrome(block, source) {
  block.dataset.echartsSource = source;
  if (!block.querySelector(".echarts-toolbar")) {
    const bar = document.createElement("div");
    bar.className = "echarts-toolbar";
    bar.innerHTML = `
      <button type="button" class="mermaid-tool-btn icon-btn" data-echarts-action="fold" title="折叠/展开" aria-label="折叠">${iconSvg("fold")}</button>
      <span class="echarts-status-inline" hidden></span>
      <span class="mermaid-toolbar-spacer"></span>
      <button type="button" class="mermaid-tool-btn icon-btn" data-echarts-action="copy" title="复制 JSON" aria-label="复制">${iconSvg("copy")}</button>
      <button type="button" class="mermaid-tool-btn icon-btn" data-echarts-action="download" title="下载 PNG" aria-label="下载">${iconSvg("download")}</button>
      <button type="button" class="mermaid-tool-btn icon-btn" data-echarts-action="fullscreen" title="全屏" aria-label="全屏">${iconSvg("fullscreen")}</button>
      <button type="button" class="mermaid-zoom-btn icon-btn" data-echarts-zoom="out" title="缩小画布" aria-label="缩小">${iconSvg("minus")}</button>
      <button type="button" class="mermaid-zoom-btn icon-btn" data-echarts-zoom="in" title="放大画布" aria-label="放大">${iconSvg("plus")}</button>
      <button type="button" class="mermaid-tool-btn icon-btn" data-echarts-action="retry" title="重新渲染" aria-label="重试">${iconSvg("retry")}</button>
      <span class="mermaid-mode-switch" role="group" aria-label="视图切换">
        <button type="button" class="mermaid-mode-btn is-active" data-echarts-action="mode-view">视图</button>
        <button type="button" class="mermaid-mode-btn" data-echarts-action="mode-source">源码</button>
      </span>
    `;
    block.insertBefore(bar, block.firstChild);
  }
  if (!block.querySelector(".echarts-viewport")) {
    const viewport = document.createElement("div");
    viewport.className = "echarts-viewport";
    const stage = document.createElement("div");
    stage.className = "echarts-stage";
    const pre = block.querySelector("pre.echarts-source");
    if (pre) {
      pre.hidden = true;
      block.appendChild(pre);
    }
    viewport.appendChild(stage);
    block.appendChild(viewport);
  }
  let sourcePre = block.querySelector("pre.echarts-source");
  if (!sourcePre) {
    sourcePre = document.createElement("pre");
    sourcePre.className = "echarts-source";
    sourcePre.hidden = true;
    block.appendChild(sourcePre);
  }
  sourcePre.textContent = source;
  block.dataset.zoom = block.dataset.zoom || "1";
  block.dataset.mode = block.dataset.mode || "view";
  applyZoom(block, Number(block.dataset.zoom) || 1);
  applyMode(block, block.dataset.mode || "view");
}

function applyZoom(block, zoom) {
  const z = Math.max(0.5, Math.min(2.5, Number(zoom) || 1));
  block.dataset.zoom = String(z);
  const stage = block.querySelector(".echarts-stage");
  if (stage) {
    const base = 320;
    stage.style.height = `${Math.round(base * z)}px`;
  }
  const chart = block._nlmChart;
  if (chart) {
    try {
      chart.resize();
    } catch {
      /* ignore */
    }
  }
}

function applyMode(block, mode) {
  block.dataset.mode = mode;
  const viewport = block.querySelector(".echarts-viewport");
  const sourcePre = block.querySelector("pre.echarts-source");
  if (viewport) viewport.hidden = mode === "source";
  if (sourcePre) sourcePre.hidden = mode !== "source";
  block.querySelectorAll(".mermaid-mode-btn").forEach((btn) => {
    const isView = btn.getAttribute("data-echarts-action") === "mode-view";
    const isSource = btn.getAttribute("data-echarts-action") === "mode-source";
    btn.classList.toggle("is-active", (mode === "view" && isView) || (mode === "source" && isSource));
  });
}

function applyCollapsed(block, collapsed) {
  block.dataset.collapsed = collapsed ? "1" : "0";
  block.classList.toggle("is-collapsed", !!collapsed);
  const viewport = block.querySelector(".echarts-viewport");
  const sourcePre = block.querySelector("pre.echarts-source");
  if (collapsed) {
    if (viewport) viewport.hidden = true;
    if (sourcePre) sourcePre.hidden = true;
  } else {
    applyMode(block, block.dataset.mode || "view");
  }
}

async function renderOne(block, option) {
  const echarts = await ensureEcharts();
  const stage = block.querySelector(".echarts-stage");
  if (!stage) return;
  if (block._nlmChart) {
    try {
      block._nlmChart.dispose();
    } catch {
      /* ignore */
    }
    block._nlmChart = null;
  }
  const polished = polishOption(option);
  const chart = echarts.init(stage, null, { renderer: "canvas" });
  chart.setOption(polished, { notMerge: true });
  block._nlmChart = chart;
  block.setAttribute("data-processed", "ok");
  setStatus(block, "");
  applyZoom(block, Number(block.dataset.zoom) || 1);
}

function polishOption(option) {
  const opt = option && typeof option === "object" ? { ...option } : {};
  if (!opt.tooltip) opt.tooltip = { trigger: "axis" };
  if (!opt.grid) {
    opt.grid = { left: 12, right: 16, top: 36, bottom: 12, containLabel: true };
  }
  if (!opt.color) {
    opt.color = ["#3a9cf0", "#2bb8a0", "#c9a227", "#a78bfa", "#e07070", "#60a5fa"];
  }
  if (Array.isArray(opt.series)) {
    opt.series = opt.series.map((s) => {
      if (!s || typeof s !== "object") return s;
      const next = { ...s };
      if (next.type === "line") {
        if (next.smooth == null) next.smooth = true;
        if (next.showSymbol == null) next.showSymbol = true;
        if (next.symbolSize == null) next.symbolSize = 6;
      }
      return next;
    });
  }
  return opt;
}

function downloadPng(block) {
  const chart = block._nlmChart;
  if (!chart) {
    setStatus(block, "暂无可下载的图", true);
    return;
  }
  try {
    const url = chart.getDataURL({
      type: "png",
      pixelRatio: 2,
      backgroundColor: getComputedStyle(document.documentElement).getPropertyValue("--panel-solid").trim() || "#0f1b2a",
    });
    const a = document.createElement("a");
    a.href = url;
    a.download = `echarts-${Date.now()}.png`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setStatus(block, "已下载 PNG", false);
    setTimeout(() => setStatus(block, ""), 1200);
  } catch (err) {
    setStatus(block, `下载失败：${err.message || err}`, true);
  }
}

function openFullscreen(block) {
  document.querySelectorAll(".echarts-fs-overlay").forEach((el) => el.remove());
  document.documentElement.classList.remove("echarts-fs-open");

  const optionRaw = block.dataset.echartsSource || "";
  let option;
  try {
    option = parseOption(optionRaw);
  } catch (err) {
    setStatus(block, `全屏失败：${err.message || err}`, true);
    return;
  }

  const overlay = document.createElement("div");
  overlay.className = "echarts-fs-overlay mermaid-fs-overlay";
  overlay.innerHTML = `
    <div class="mermaid-fs-panel" role="dialog" aria-modal="true" aria-label="ECharts 全屏">
      <div class="mermaid-fs-toolbar">
        <span class="mermaid-fs-title">ECharts · 滚轮缩放 · 拖拽平移（图表内置）</span>
        <div class="mermaid-fs-tools">
          <button type="button" class="mermaid-tool-btn" data-fs-download="1">下载 PNG</button>
          <button type="button" class="mermaid-tool-btn" data-fs-close="1">关闭</button>
        </div>
      </div>
      <div class="echarts-fs-viewport mermaid-fs-viewport" tabindex="0">
        <div class="echarts-fs-stage"></div>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);
  document.documentElement.classList.add("echarts-fs-open");

  const stage = overlay.querySelector(".echarts-fs-stage");
  let chart = null;
  ensureEcharts().then((echarts) => {
    chart = echarts.init(stage, null, { renderer: "canvas" });
    const opt = { ...option };
    if (!opt.dataZoom) {
      opt.dataZoom = [
        { type: "inside" },
        { type: "slider", height: 18, bottom: 8 },
      ];
    }
    chart.setOption(opt, { notMerge: true });
    overlay._nlmChart = chart;
    const onResize = () => chart && chart.resize();
    window.addEventListener("resize", onResize);
    overlay._nlmFsCleanup = () => {
      window.removeEventListener("resize", onResize);
      try {
        chart?.dispose();
      } catch {
        /* ignore */
      }
    };
    setTimeout(onResize, 50);
  });

  const close = () => {
    if (typeof overlay._nlmFsCleanup === "function") overlay._nlmFsCleanup();
    overlay.remove();
    document.documentElement.classList.remove("echarts-fs-open");
    document.removeEventListener("keydown", onKey);
  };
  const onKey = (ev) => {
    if (ev.key === "Escape") close();
  };
  document.addEventListener("keydown", onKey);
  overlay.addEventListener("click", (ev) => {
    if (ev.target === overlay || ev.target.closest?.("[data-fs-close]")) close();
    if (ev.target.closest?.("[data-fs-download]")) {
      const c = overlay._nlmChart;
      if (!c) return;
      const url = c.getDataURL({ type: "png", pixelRatio: 2, backgroundColor: "#0f1b2a" });
      const a = document.createElement("a");
      a.href = url;
      a.download = `echarts-${Date.now()}.png`;
      a.click();
    }
  });
}

function bindControls(root) {
  if (!root || root._nlmEchartsControls) return;
  root._nlmEchartsControls = true;
  root.addEventListener("click", async (ev) => {
    const zoomBtn = ev.target?.closest?.("[data-echarts-zoom]");
    const actionBtn = ev.target?.closest?.("[data-echarts-action]");
    const block = (zoomBtn || actionBtn)?.closest?.(".echarts-block");
    if (!block || !root.contains(block)) return;

    if (zoomBtn) {
      const action = zoomBtn.getAttribute("data-echarts-zoom");
      const cur = Number(block.dataset.zoom) || 1;
      if (action === "in") applyZoom(block, cur + 0.15);
      else if (action === "out") applyZoom(block, cur - 0.15);
      return;
    }

    const action = actionBtn?.getAttribute("data-echarts-action");
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
      try {
        await navigator.clipboard.writeText(block.dataset.echartsSource || "");
        setStatus(block, "已复制", false);
        setTimeout(() => setStatus(block, ""), 900);
      } catch {
        setStatus(block, "复制失败", true);
      }
      return;
    }
    if (action === "download") {
      downloadPng(block);
      return;
    }
    if (action === "fullscreen") {
      openFullscreen(block);
      return;
    }
    if (action === "retry" && typeof block._nlmRetry === "function") {
      await block._nlmRetry();
    }
  });
}

export async function renderEchartsIn(root, { streaming = false } = {}) {
  if (!root) return;
  bindControls(root);
  void streaming;
  const blocks = [...root.querySelectorAll(".echarts-block")];
  if (!blocks.length) return;

  for (const block of blocks) {
    const pre = block.querySelector("pre.echarts-source");
    const original = block.dataset.echartsSource || pre?.textContent || "";
    if (!original.trim()) continue;

    // Skip re-init if same source already ok
    if (
      block.getAttribute("data-processed") === "ok" &&
      block.dataset.echartsSource === original &&
      block._nlmChart
    ) {
      continue;
    }

    ensureChrome(block, original);
    block._nlmRetry = async () => {
      try {
        const opt = parseOption(block.dataset.echartsSource || original);
        await renderOne(block, opt);
      } catch (err) {
        block.setAttribute("data-processed", "error");
        setStatus(block, `渲染失败：${err.message || err}`, true);
      }
    };

    try {
      const opt = parseOption(original);
      await renderOne(block, opt);
    } catch (err) {
      block.setAttribute("data-processed", "error");
      setStatus(block, `JSON/渲染错误：${err.message || err}`, true);
    }
  }
}
