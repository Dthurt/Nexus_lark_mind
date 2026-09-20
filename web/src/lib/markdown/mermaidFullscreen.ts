/** Mermaid fullscreen: crisp SVG size zoom + pan (no CSS scale blur). */

import { diagramInk, diagramPanelBg, mermaidThemeName } from "./diagramTheme";

function iconSvg(name: string) {
  const common =
    'width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"';
  if (name === "minus") {
    return `<svg ${common}><line x1="5" y1="12" x2="19" y2="12"/></svg>`;
  }
  if (name === "plus") {
    return `<svg ${common}><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>`;
  }
  return "";
}

export function closeMermaidFullscreen() {
  document.querySelectorAll(".mermaid-fs-overlay").forEach((el: any) => {
    if (typeof el._nlmFsCleanup === "function") el._nlmFsCleanup();
    el.remove();
  });
  document.documentElement.classList.remove("mermaid-fs-open");
}

async function renderSvgFromSource(source: string): Promise<SVGSVGElement | null> {
  const text = (source || "").trim();
  if (!text) return null;
  const mod = await import("mermaid");
  const mermaid = (mod as any).default || mod;
  const theme = mermaidThemeName();
  mermaid.initialize({
    startOnLoad: false,
    securityLevel: "loose",
    theme,
    themeVariables: {
      background: diagramPanelBg(),
      primaryTextColor: diagramInk(),
    },
  });
  const id = `nlm-mmd-fs-${Date.now()}`;
  try {
    const result = await mermaid.render(id, text);
    const svgHtml = typeof result === "string" ? result : result?.svg;
    if (!svgHtml) return null;
    const wrap = document.createElement("div");
    wrap.innerHTML = svgHtml;
    return wrap.querySelector("svg");
  } finally {
    document.querySelectorAll(`svg[id^="${id}"], [id^="${id}"], [id^="d${id}"]`).forEach((n) => {
      if ((n as HTMLElement).closest?.(".mermaid-stage, .mermaid-block, .mermaid-fs-overlay")) {
        return;
      }
      n.remove();
    });
  }
}

function mountSvg(
  fsStage: HTMLElement,
  srcSvg: SVGSVGElement,
): { svgEl: SVGSVGElement; baseW: number; baseH: number } {
  const svgEl = srcSvg.cloneNode(true) as SVGSVGElement;
  svgEl.removeAttribute("style");
  svgEl.style.maxWidth = "none";
  svgEl.style.height = "auto";
  svgEl.style.display = "block";
  const vb = svgEl.viewBox?.baseVal;
  let baseW = 400;
  let baseH = 300;
  const wAttr = parseFloat(svgEl.getAttribute("width") || "");
  const hAttr = parseFloat(svgEl.getAttribute("height") || "");
  if (vb && vb.width > 0 && vb.height > 0) {
    baseW = vb.width;
    baseH = vb.height;
  } else if (wAttr > 0 && hAttr > 0 && !/%/.test(String(svgEl.getAttribute("width") || ""))) {
    baseW = wAttr;
    baseH = hAttr;
  } else {
    try {
      const b = srcSvg.getBBox?.();
      if (b && b.width > 1 && b.height > 1) {
        baseW = b.width;
        baseH = b.height;
      }
    } catch {
      /* ignore */
    }
  }
  if (!svgEl.getAttribute("viewBox")) {
    svgEl.setAttribute("viewBox", `0 0 ${baseW} ${baseH}`);
  }
  svgEl.setAttribute("width", String(baseW));
  svgEl.setAttribute("height", String(baseH));
  svgEl.setAttribute("preserveAspectRatio", "xMidYMid meet");
  fsStage.innerHTML = "";
  fsStage.appendChild(svgEl);
  return { svgEl, baseW, baseH };
}

export function openMermaidFullscreen(block: HTMLElement) {
  closeMermaidFullscreen();
  const source =
    block.dataset.mermaidSource ||
    block.querySelector("pre.mermaid-source, pre.mermaid")?.textContent ||
    "";
  const stage = block.querySelector(".mermaid-stage");
  const overlay = document.createElement("div");
  overlay.className = "mermaid-fs-overlay";
  overlay.innerHTML = `
    <div class="mermaid-fs-panel" role="dialog" aria-modal="true" aria-label="Mermaid 全屏">
      <div class="mermaid-fs-toolbar">
        <span class="mermaid-fs-title">Mermaid · 拖拽移动 · +/− 缩放</span>
        <div class="mermaid-fs-tools">
          <button type="button" class="mermaid-tool-btn icon-btn" data-fs-zoom="out" title="缩小" aria-label="缩小">${iconSvg("minus")}</button>
          <span class="mermaid-fs-zoom-label" data-fs-zoom-label>100%</span>
          <button type="button" class="mermaid-tool-btn icon-btn" data-fs-zoom="in" title="放大" aria-label="放大">${iconSvg("plus")}</button>
          <button type="button" class="mermaid-tool-btn" data-fs-zoom="fit" title="适应窗口">适应</button>
          <button type="button" class="mermaid-tool-btn" data-fs-zoom="reset" title="重置">1:1</button>
          <button type="button" class="mermaid-tool-btn" data-fs-close="1">关闭</button>
        </div>
      </div>
      <div class="mermaid-fs-viewport" tabindex="0">
        <div class="mermaid-fs-stage"><div class="mermaid-fs-loading">渲染中…</div></div>
      </div>
    </div>
  `;
  const viewport = overlay.querySelector(".mermaid-fs-viewport") as HTMLElement;
  const fsStage = overlay.querySelector(".mermaid-fs-stage") as HTMLElement;
  const zoomLabel = overlay.querySelector("[data-fs-zoom-label]");
  const srcSvg = stage?.querySelector("svg") as SVGSVGElement | null;

  let svgEl: SVGSVGElement | null = null;
  let baseW = 400;
  let baseH = 300;

  const state = { zoom: 1, x: 0, y: 0, dragging: false, lastX: 0, lastY: 0 };

  function applyView() {
    if (svgEl) {
      svgEl.setAttribute("width", String(Math.max(1, baseW * state.zoom)));
      svgEl.setAttribute("height", String(Math.max(1, baseH * state.zoom)));
    }
    fsStage.style.transform = `translate(${state.x}px, ${state.y}px)`;
    if (zoomLabel) zoomLabel.textContent = `${Math.round(state.zoom * 100)}%`;
  }

  function fitToViewport(pad = 32) {
    const vr = viewport.getBoundingClientRect();
    if (!vr.width || !vr.height || !baseW || !baseH) return;
    const zx = (vr.width - pad * 2) / baseW;
    const zy = (vr.height - pad * 2) / baseH;
    state.zoom = Math.min(12, Math.max(0.15, Math.min(zx, zy)));
    const w = baseW * state.zoom;
    const h = baseH * state.zoom;
    state.x = (vr.width - w) / 2;
    state.y = (vr.height - h) / 2;
    applyView();
  }

  function zoomBy(delta: number, cx?: number | null, cy?: number | null) {
    const vr = viewport.getBoundingClientRect();
    const originX = cx == null ? vr.width / 2 : cx - vr.left;
    const originY = cy == null ? vr.height / 2 : cy - vr.top;
    const prev = state.zoom;
    const next = Math.min(16, Math.max(0.1, prev * (delta > 0 ? 1.18 : 1 / 1.18)));
    if (Math.abs(next - prev) < 1e-6) return;
    const relX = (originX - state.x) / (baseW * prev || 1);
    const relY = (originY - state.y) / (baseH * prev || 1);
    state.zoom = next;
    state.x = originX - relX * baseW * next;
    state.y = originY - relY * baseH * next;
    applyView();
  }

  function onToolbarClick(ev: MouseEvent) {
    const target = ev.target as HTMLElement | null;
    if (target?.closest?.("[data-fs-close]")) {
      closeMermaidFullscreen();
      return;
    }
    const zbtn = target?.closest?.("[data-fs-zoom]");
    if (!zbtn) return;
    const action = zbtn.getAttribute("data-fs-zoom");
    if (action === "in") zoomBy(1);
    else if (action === "out") zoomBy(-1);
    else if (action === "fit") fitToViewport();
    else if (action === "reset") {
      state.zoom = 1;
      const vr = viewport.getBoundingClientRect();
      state.x = (vr.width - baseW) / 2;
      state.y = (vr.height - baseH) / 2;
      applyView();
    }
  }

  function onPointerDown(ev: PointerEvent) {
    if (ev.button !== 0) return;
    if ((ev.target as HTMLElement)?.closest?.(".mermaid-fs-toolbar")) return;
    state.dragging = true;
    state.lastX = ev.clientX;
    state.lastY = ev.clientY;
    viewport.classList.add("is-dragging");
    viewport.setPointerCapture?.(ev.pointerId);
  }

  function onPointerMove(ev: PointerEvent) {
    if (!state.dragging) return;
    state.x += ev.clientX - state.lastX;
    state.y += ev.clientY - state.lastY;
    state.lastX = ev.clientX;
    state.lastY = ev.clientY;
    applyView();
  }

  function onPointerUp(ev: PointerEvent) {
    if (!state.dragging) return;
    state.dragging = false;
    viewport.classList.remove("is-dragging");
    try {
      viewport.releasePointerCapture?.(ev.pointerId);
    } catch {
      /* ignore */
    }
  }

  function onWheel(ev: WheelEvent) {
    ev.preventDefault();
    zoomBy(ev.deltaY < 0 ? 1 : -1, ev.clientX, ev.clientY);
  }

  function onKey(ev: KeyboardEvent) {
    if (ev.key === "Escape") closeMermaidFullscreen();
    else if (ev.key === "+" || ev.key === "=") {
      ev.preventDefault();
      zoomBy(1);
    } else if (ev.key === "-" || ev.key === "_") {
      ev.preventDefault();
      zoomBy(-1);
    } else if (ev.key === "0") {
      ev.preventDefault();
      fitToViewport();
    }
  }

  function afterSvgReady() {
    const tryFit = (n = 0) => {
      const vr = viewport.getBoundingClientRect();
      if ((!vr.width || !vr.height) && n < 12) {
        requestAnimationFrame(() => tryFit(n + 1));
        return;
      }
      if (svgEl) {
        try {
          const b = svgEl.getBBox();
          if (b.width > 1 && b.height > 1) {
            baseW = b.width;
            baseH = b.height;
            if (!svgEl.getAttribute("viewBox")) {
              svgEl.setAttribute("viewBox", `${b.x} ${b.y} ${b.width} ${b.height}`);
            }
          }
        } catch {
          /* ignore */
        }
      }
      fitToViewport();
      viewport.focus?.({ preventScroll: true });
    };
    requestAnimationFrame(() => tryFit(0));
  }

  overlay.addEventListener("click", onToolbarClick as any);
  overlay.addEventListener("click", (ev) => {
    if (ev.target === overlay) closeMermaidFullscreen();
  });
  viewport.addEventListener("pointerdown", onPointerDown);
  viewport.addEventListener("pointermove", onPointerMove);
  viewport.addEventListener("pointerup", onPointerUp);
  viewport.addEventListener("pointercancel", onPointerUp);
  viewport.addEventListener("wheel", onWheel, { passive: false });
  document.addEventListener("keydown", onKey);
  (overlay as any)._nlmFsCleanup = () => document.removeEventListener("keydown", onKey);

  document.body.appendChild(overlay);
  document.documentElement.classList.add("mermaid-fs-open");

  void (async () => {
    let ready: SVGSVGElement | null = srcSvg;
    if (!ready) {
      try {
        ready = await renderSvgFromSource(source);
      } catch {
        ready = null;
      }
    }
    if (!ready) {
      fsStage.innerHTML = "";
      const pre = document.createElement("pre");
      pre.className = "mermaid-fs-source";
      pre.textContent = source || "（无 Mermaid 源码，无法渲染视图）";
      fsStage.appendChild(pre);
      return;
    }
    const mounted = mountSvg(fsStage, ready);
    svgEl = mounted.svgEl;
    baseW = mounted.baseW;
    baseH = mounted.baseH;
    afterSvgReady();
  })();
}
