import { diagramPanelBg, isLightDiagramTheme } from "./diagramTheme";

/** ECharts fenced blocks — ```echarts / ```echart JSON option. */

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

export function isEchartsLang(lang: string) {
  const k = String(lang || "").toLowerCase();
  return k === "echarts" || k === "echart" || k === "echarts-json";
}

/** Heuristic: JSON that looks like an ECharts option object. */
export function looksLikeEchartsOption(text: string) {
  const s = String(text || "").trim();
  if (!s.startsWith("{") || s.length < 24) return false;
  const hasSeries = /"series"\s*:/.test(s);
  const hasAxis = /"(xAxis|yAxis|radar|geo|angleAxis|radiusAxis)"\s*:/.test(s);
  const hasChartType =
    /"type"\s*:\s*"(line|bar|pie|scatter|radar|heatmap|funnel|gauge|candlestick|boxplot)"/.test(s);
  return hasSeries && (hasAxis || hasChartType);
}

export function echartsMarkdownHtml(source: string) {
  return `<div class="echarts-block" data-echarts-host="1"><pre class="echarts-source">${escapeHtml(source)}</pre></div>`;
}

function extractBalancedObject(src: string, from: number) {
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
export function normalizeEchartsMarkdown(raw: string) {
  let text = String(raw || "");
  if (!text) return text;

  // ```json / ```javascript with echarts-like body → ```echarts
  text = text.replace(/```(?:json|javascript|js)\s*\n([\s\S]*?)```/gi, (full: string, body: string) => {
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
  let m: RegExpExecArray | null;
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

let echartsMod: any = null;
async function ensureEcharts() {
  if (!echartsMod) {
    const mod: any = await import("echarts");
    echartsMod = mod?.default && typeof mod.default.init === "function" ? mod.default : mod;
  }
  return echartsMod;
}

/** Dispose chart instances before React replaces markdown DOM (avoids zr `.get` crashes). */
export function disposeEchartsIn(root: HTMLElement | null) {
  if (!root) return;
  root.querySelectorAll(".echarts-block").forEach((block) => {
    const el = block as any;
    if (!el._nlmChart) return;
    try {
      el._nlmChart.dispose?.();
    } catch {
      /* ignore */
    }
    el._nlmChart = null;
  });
}

/** Parse ECharts option JSON from fence body (tolerates model quirks). */
export function parseEchartsOption(raw: string) {
  let text = String(raw || "").trim();
  if (!text) throw new Error("empty echarts option");
  text = text
    .replace(/^```(?:echarts|echart|echarts-json|json)?\s*/i, "")
    .replace(/```\s*$/i, "")
    .trim();
  const start = text.indexOf("{");
  const end = text.lastIndexOf("}");
  if (start >= 0 && end > start) text = text.slice(start, end + 1);
  // Tolerate trailing commas / smart quotes common in model output
  text = text.replace(/,\s*([}\]])/g, "$1");
  text = text.replace(/[“”]/g, '"').replace(/[‘’]/g, "'");
  return JSON.parse(text);
}

function parseOption(raw: string) {
  return parseEchartsOption(raw);
}

function asArray<T>(v: T | T[] | null | undefined): T[] {
  if (v == null) return [];
  return Array.isArray(v) ? v : [v];
}

function coerceData(data: any): any[] | undefined {
  if (data == null) return undefined;
  if (Array.isArray(data)) return data;
  if (typeof data === "object") return Object.values(data);
  return undefined;
}

/** Normalize LLM option quirks that make ECharts throw (`…reading 'get'`). */
function sanitizeOption(option: any) {
  if (!option || typeof option !== "object" || Array.isArray(option)) {
    throw new Error("option 必须是 JSON 对象");
  }
  const opt: any = { ...option };

  if (opt.series != null) opt.series = asArray(opt.series).filter((s: any) => s && typeof s === "object");
  if (!opt.series?.length && !opt.dataset) {
    throw new Error("缺少 series / dataset");
  }

  if (Array.isArray(opt.series)) {
    opt.series = opt.series.map((s: any, i: number) => {
      const next = { ...s };
      if (!next.type || typeof next.type !== "string") {
        next.type = typeof opt.dataset !== "undefined" ? "line" : "bar";
      }
      const data = coerceData(next.data);
      if (data) next.data = data;
      else if (next.data != null && !Array.isArray(next.data)) delete next.data;
      if (next.name == null) next.name = `系列${i + 1}`;
      // Drop broken nested refs models often invent
      if (next.encode && typeof next.encode !== "object") delete next.encode;
      return next;
    });
  }

  for (const key of ["xAxis", "yAxis", "radiusAxis", "angleAxis", "radar"]) {
    if (opt[key] == null) continue;
    if (typeof opt[key] !== "object") {
      delete opt[key];
      continue;
    }
    if (Array.isArray(opt[key])) {
      opt[key] = opt[key].filter((a: any) => a && typeof a === "object").map((a: any) => {
        const axis = { ...a };
        const d = coerceData(axis.data);
        if (d) axis.data = d;
        return axis;
      });
      if (!opt[key].length) delete opt[key];
    } else {
      const d = coerceData(opt[key].data);
      if (d) opt[key] = { ...opt[key], data: d };
    }
  }

  if (opt.color != null && !Array.isArray(opt.color) && typeof opt.color !== "string") {
    delete opt.color;
  }
  for (const key of ["visualMap", "calendar", "geo", "graphic", "timeline", "brush", "toolbox"]) {
    if (opt[key] == null) delete opt[key];
  }

  return polishOption(opt);
}

function setStatus(block: HTMLElement, text: string, isError = false) {
  const el = block.querySelector(".echarts-status-inline") as HTMLElement | null;
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

function ensureChrome(block: HTMLElement, source: string) {
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
      <button type="button" class="mermaid-tool-btn" data-echarts-action="canvas" title="在 Canvas 打开">Canvas</button>
      <button type="button" class="mermaid-zoom-btn icon-btn" data-echarts-zoom="out" title="缩小画布" aria-label="缩小">${iconSvg("minus")}</button>
      <button type="button" class="mermaid-zoom-btn icon-btn" data-echarts-zoom="in" title="放大画布" aria-label="放大">${iconSvg("plus")}</button>
      <button type="button" class="mermaid-tool-btn icon-btn" data-echarts-action="retry" title="重新渲染" aria-label="重试">${iconSvg("retry")}</button>
      <span class="mermaid-mode-switch" role="group" aria-label="视图切换">
        <button type="button" class="mermaid-mode-btn is-active" data-echarts-action="mode-view">视图</button>
        <button type="button" class="mermaid-mode-btn" data-echarts-action="mode-source">源码</button>
      </span>
    `;
    block.insertBefore(bar, block.firstChild);
  } else if (!block.querySelector('[data-echarts-action="canvas"]')) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "mermaid-tool-btn";
    btn.setAttribute("data-echarts-action", "canvas");
    btn.title = "在 Canvas 打开";
    btn.textContent = "Canvas";
    const fs = block.querySelector('[data-echarts-action="fullscreen"]');
    if (fs?.nextSibling) fs.parentElement?.insertBefore(btn, fs.nextSibling);
    else block.querySelector(".echarts-toolbar")?.appendChild(btn);
  }
  if (!block.querySelector(".echarts-viewport")) {
    const viewport = document.createElement("div");
    viewport.className = "echarts-viewport";
    const stage = document.createElement("div");
    stage.className = "echarts-stage";
    const pre = block.querySelector("pre.echarts-source") as HTMLElement | null;
    if (pre) {
      pre.hidden = true;
      block.appendChild(pre);
    }
    viewport.appendChild(stage);
    block.appendChild(viewport);
  }
  let sourcePre = block.querySelector("pre.echarts-source") as HTMLElement | null;
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

function applyZoom(block: any, zoom: number) {
  const z = Math.max(0.5, Math.min(2.5, Number(zoom) || 1));
  block.dataset.zoom = String(z);
  const stage = block.querySelector(".echarts-stage") as HTMLElement | null;
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

function applyMode(block: HTMLElement, mode: string) {
  block.dataset.mode = mode;
  const viewport = block.querySelector(".echarts-viewport") as HTMLElement | null;
  const sourcePre = block.querySelector("pre.echarts-source") as HTMLElement | null;
  if (viewport) viewport.hidden = mode === "source";
  if (sourcePre) sourcePre.hidden = mode !== "source";
  block.querySelectorAll(".mermaid-mode-btn").forEach((btn) => {
    const isView = btn.getAttribute("data-echarts-action") === "mode-view";
    const isSource = btn.getAttribute("data-echarts-action") === "mode-source";
    btn.classList.toggle("is-active", (mode === "view" && isView) || (mode === "source" && isSource));
  });
}

function applyCollapsed(block: HTMLElement, collapsed: boolean) {
  block.dataset.collapsed = collapsed ? "1" : "0";
  block.classList.toggle("is-collapsed", !!collapsed);
  const viewport = block.querySelector(".echarts-viewport") as HTMLElement | null;
  const sourcePre = block.querySelector("pre.echarts-source") as HTMLElement | null;
  if (collapsed) {
    if (viewport) viewport.hidden = true;
    if (sourcePre) sourcePre.hidden = true;
  } else {
    applyMode(block, block.dataset.mode || "view");
  }
}

async function renderOne(block: any, option: any) {
  const echarts = await ensureEcharts();
  if (!echarts || typeof echarts.init !== "function") {
    throw new Error("ECharts 未能加载");
  }
  ensureChrome(block, block.dataset.echartsSource || "");
  const stage = block.querySelector(".echarts-stage") as HTMLElement | null;
  if (!stage) throw new Error("缺少图表容器");
  // Hidden / 0-size stages make zrender blow up on internal `.get`
  if (block.dataset.collapsed === "1") applyCollapsed(block, false);
  if (block.dataset.mode === "source") applyMode(block, "view");
  stage.style.minHeight = stage.style.minHeight || "160px";
  stage.style.width = stage.style.width || "100%";

  if (block._nlmChart) {
    try {
      block._nlmChart.dispose();
    } catch {
      /* ignore */
    }
    block._nlmChart = null;
  }
  const polished = sanitizeOption(option);
  const chart = echarts.init(stage, undefined, { renderer: "canvas", width: "auto", height: "auto" });
  try {
    chart.setOption(polished, { notMerge: true, lazyUpdate: false });
  } catch (err) {
    try {
      chart.dispose();
    } catch {
      /* ignore */
    }
    block._nlmChart = null;
    throw err;
  }
  block._nlmChart = chart;
  block.setAttribute("data-processed", "ok");
  setStatus(block, "");
  applyZoom(block, Number(block.dataset.zoom) || 1);
  requestAnimationFrame(() => {
    try {
      chart.resize();
    } catch {
      /* ignore */
    }
  });
}

function polishOption(option: any) {
  const opt = option && typeof option === "object" ? { ...option } : {};
  if (!opt.tooltip) opt.tooltip = { trigger: "axis" };
  if (!opt.grid) {
    opt.grid = { left: 12, right: 16, top: 36, bottom: 12, containLabel: true };
  }
  if (!opt.color) {
    opt.color = ["#3a9cf0", "#2bb8a0", "#c9a227", "#a78bfa", "#e07070", "#60a5fa"];
  }
  if (opt.backgroundColor == null) {
    opt.backgroundColor = diagramPanelBg();
  }
  const light = isLightDiagramTheme();
  const axisColor = light ? "#334155" : "#94a3b8";
  const splitColor = light ? "rgba(15,23,42,0.08)" : "rgba(148,163,184,0.16)";
  const applyAxis = (axis: any) => {
    if (!axis || typeof axis !== "object") return axis;
    const next = { ...axis };
    next.axisLabel = { ...(next.axisLabel || {}), color: axisColor };
    next.axisLine = {
      ...(next.axisLine || {}),
      lineStyle: { ...((next.axisLine && next.axisLine.lineStyle) || {}), color: splitColor },
    };
    next.splitLine = {
      ...(next.splitLine || {}),
      lineStyle: { ...((next.splitLine && next.splitLine.lineStyle) || {}), color: splitColor },
    };
    return next;
  };
  if (opt.xAxis) {
    opt.xAxis = Array.isArray(opt.xAxis) ? opt.xAxis.map(applyAxis) : applyAxis(opt.xAxis);
  }
  if (opt.yAxis) {
    opt.yAxis = Array.isArray(opt.yAxis) ? opt.yAxis.map(applyAxis) : applyAxis(opt.yAxis);
  }
  if (!opt.textStyle) {
    opt.textStyle = { color: light ? "#0f172a" : "#e2e8f0" };
  }
  if (Array.isArray(opt.series)) {
    opt.series = opt.series.map((s: any) => {
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

function downloadPng(block: any) {
  const chart = block._nlmChart;
  if (!chart) {
    setStatus(block, "暂无可下载的图", true);
    return;
  }
  try {
    const url = chart.getDataURL({
      type: "png",
      pixelRatio: 2,
      backgroundColor: diagramPanelBg(),
    });
    const a = document.createElement("a");
    a.href = url;
    a.download = `echarts-${Date.now()}.png`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setStatus(block, "已下载 PNG", false);
    setTimeout(() => setStatus(block, ""), 1200);
  } catch (err: any) {
    setStatus(block, `下载失败：${err.message || err}`, true);
  }
}

function openFullscreen(block: HTMLElement) {
  document.querySelectorAll(".echarts-fs-overlay").forEach((el) => el.remove());
  document.documentElement.classList.remove("echarts-fs-open");

  const optionRaw = block.dataset.echartsSource || "";
  let option: any;
  try {
    option = parseOption(optionRaw);
  } catch (err: any) {
    setStatus(block, `全屏失败：${err.message || err}`, true);
    return;
  }

  const overlay: any = document.createElement("div");
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
  let chart: any = null;
  ensureEcharts().then((echarts) => {
    if (!stage || typeof echarts.init !== "function") return;
    try {
      chart = echarts.init(stage, undefined, { renderer: "canvas" });
      chart.setOption(sanitizeOption(option), { notMerge: true });
    } catch (err: any) {
      setStatus(block, `全屏失败：${err?.message || err}`, true);
      close();
      return;
    }
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
  const onKey = (ev: KeyboardEvent) => {
    if (ev.key === "Escape") close();
  };
  document.addEventListener("keydown", onKey);
  overlay.addEventListener("click", (ev: MouseEvent) => {
    if (ev.target === overlay || (ev.target as HTMLElement).closest?.("[data-fs-close]")) close();
    if ((ev.target as HTMLElement).closest?.("[data-fs-download]")) {
      const c = overlay._nlmChart;
      if (!c) return;
      const url = c.getDataURL({ type: "png", pixelRatio: 2, backgroundColor: diagramPanelBg() });
      const a = document.createElement("a");
      a.href = url;
      a.download = `echarts-${Date.now()}.png`;
      a.click();
    }
  });
}

function bindControls(root: any) {
  if (!root || root._nlmEchartsControls) return;
  root._nlmEchartsControls = true;
  root.addEventListener("click", async (ev: MouseEvent) => {
    const target = ev.target as HTMLElement;
    const zoomBtn = target?.closest?.("[data-echarts-zoom]");
    const actionBtn = target?.closest?.("[data-echarts-action]");
    const block = (zoomBtn || actionBtn)?.closest?.(".echarts-block") as any;
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
      if (!block._nlmChart && typeof block._nlmRetry === "function") {
        await block._nlmRetry();
      } else if (block._nlmChart) {
        try {
          block._nlmChart.resize();
        } catch {
          /* ignore */
        }
      }
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
    if (action === "canvas") {
      const body = (block.dataset.echartsSource || block.querySelector("pre.echarts-source")?.textContent || "").trim();
      if (body) {
        window.dispatchEvent(
          new CustomEvent("nlm-canvas-open", {
            detail: {
              kind: "echarts",
              title: "ECharts",
              body,
              dedupeKey: `echarts:${body.slice(0, 80)}`,
            },
          }),
        );
      }
      return;
    }
    if (action === "retry" && typeof block._nlmRetry === "function") {
      await block._nlmRetry();
    }
  });
}

function extractEchartsSource(raw: string) {
  const text = String(raw || "").trim();
  if (!text) return "";
  const fenced = text.match(/```(?:echarts|echart|echarts-json|json)\s*([\s\S]*?)```/i);
  if (fenced) return fenced[1].trim();
  const start = text.indexOf("{");
  const end = text.lastIndexOf("}");
  if (start >= 0 && end > start) return text.slice(start, end + 1).trim();
  return text;
}

function failToSource(block: any, message: string) {
  block.setAttribute("data-processed", "error");
  setStatus(block, message, true);
  applyMode(block, "source");
}

export async function renderEchartsIn(
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
  const blocks = [...root.querySelectorAll(".echarts-block")] as any[];
  if (!blocks.length) return;

  // Incomplete fences during stream → skip init (source preview only)
  if (streaming) {
    for (const block of blocks) {
      if (block.getAttribute("data-processed") === "ok" && block._nlmChart) continue;
      const pre = block.querySelector("pre.echarts-source");
      const original = block.dataset.echartsSource || pre?.textContent || "";
      if (!original.trim()) continue;
      ensureChrome(block, original);
      applyMode(block, "source");
      setStatus(block, "生成中…");
      block.setAttribute("data-processed", "pending");
    }
    return;
  }

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

    const attemptRender = async (
      src: string,
      { allowRepair = true }: { allowRepair?: boolean } = {}
    ) => {
      let source = src;
      let lastErr: any = null;

      try {
        const opt = parseOption(source);
        await renderOne(block, opt);
        ensureChrome(block, source);
        applyMode(block, "view");
        return true;
      } catch (err: any) {
        lastErr = err;
      }

      if (allowRepair && typeof repair === "function") {
        const reason = String(lastErr?.message || lastErr || "unknown");
        setStatus(block, "渲染失败，正在重新生成…", true);
        applyMode(block, "source");
        try {
          const fixedRaw = await repair(source, reason);
          const fixed = extractEchartsSource(fixedRaw || "");
          if (fixed) {
            ensureChrome(block, fixed);
            const opt = parseOption(fixed);
            await renderOne(block, opt);
            applyMode(block, "view");
            if (fixed !== original && typeof onFixed === "function") {
              onFixed({ from: original, to: fixed });
            }
            return true;
          }
          lastErr = new Error(`修复未返回可用 JSON（原错误：${reason}）`);
        } catch (err: any) {
          lastErr = new Error(
            `修复失败：${err?.message || err}｜原错误：${reason}`
          );
        }
      }

      ensureChrome(block, source);
      failToSource(block, `JSON/渲染错误：${lastErr?.message || lastErr}`);
      return false;
    };

    block._nlmRetry = async () => {
      block.removeAttribute("data-processed");
      setStatus(block, "重试中…");
      await attemptRender(block.dataset.echartsSource || original, { allowRepair: true });
    };

    await attemptRender(original, { allowRepair: true });
  }
}
