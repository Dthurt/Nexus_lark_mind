/**
 * Interactive mindmap (markdown outline / indented tree).
 * Fence: ```mindmap
 * Same chrome pattern as Draw.io / Mermaid (fold, copy, fullscreen).
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
  return "";
}

export function isMindmapLang(lang: string) {
  const k = String(lang || "").toLowerCase();
  return k === "mindmap" || k === "mind-map" || k === "markmap";
}

type MindNode = { id: string; text: string; children: MindNode[]; open: boolean };

function parseMindmap(raw: string): MindNode {
  let text = String(raw || "")
    .replace(/^```(?:mindmap|mind-map|markmap)\s*/i, "")
    .replace(/```\s*$/i, "")
    .replace(/^mindmap\s*/i, "")
    .trim();
  const lines = text.split(/\r?\n/).filter((l) => l.trim().length);
  const root: MindNode = { id: "n0", text: "Root", children: [], open: true };
  if (!lines.length) return root;

  const stack: { depth: number; node: MindNode }[] = [{ depth: -1, node: root }];
  let seq = 0;
  for (const line of lines) {
    const m = line.match(/^(\s*)([-*+]|\d+\.)?\s*(.+)$/);
    if (!m) continue;
    const indent = m[1].replace(/\t/g, "  ").length;
    const depth = Math.floor(indent / 2);
    const label = m[3].replace(/^root\b[:\s]*/i, "").trim() || "…";
    seq += 1;
    const node: MindNode = { id: `n${seq}`, text: label, children: [], open: true };
    while (stack.length > 1 && stack[stack.length - 1].depth >= depth) stack.pop();
    stack[stack.length - 1].node.children.push(node);
    stack.push({ depth, node });
  }
  if (root.children.length === 1 && root.text === "Root") {
    return { ...root.children[0], open: true };
  }
  if (root.children.length) root.text = root.children[0].text === "Root" ? "Mindmap" : root.text;
  return root;
}

export function mindmapMarkdownHtml(text: string) {
  return `<div class="mindmap-block" data-mindmap-host="1"><pre class="mindmap-source">${escapeHtml(text)}</pre></div>`;
}

function setStatus(block: HTMLElement, text: string, isError = false) {
  const el = block.querySelector(".mindmap-status-inline") as HTMLElement | null;
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

function layout(node: MindNode, depth = 0, yRef = { y: 0 }): { nodes: any[]; edges: any[]; height: number } {
  const nodes: any[] = [];
  const edges: any[] = [];
  const x = 24 + depth * 160;
  const y = yRef.y;
  nodes.push({ id: node.id, text: node.text, x, y, depth, open: node.open, hasKids: node.children.length > 0 });
  yRef.y += 44;
  if (node.open) {
    for (const child of node.children) {
      const before = yRef.y;
      const sub = layout(child, depth + 1, yRef);
      nodes.push(...sub.nodes);
      edges.push(...sub.edges);
      edges.push({ from: node.id, to: child.id, x1: x + 120, y1: y + 14, x2: 24 + (depth + 1) * 160, y2: before + 14 });
    }
  }
  return { nodes, edges, height: yRef.y };
}

function renderSvg(block: HTMLElement, root: MindNode) {
  const stage = block.querySelector(".mindmap-stage") as HTMLElement | null;
  if (!stage) return;
  const { nodes, edges, height } = layout(root);
  const width = Math.max(480, ...nodes.map((n) => n.x + 140));
  const ink = getComputedStyle(document.documentElement).getPropertyValue("--ink").trim() || "#c8d2dc";
  const line = getComputedStyle(document.documentElement).getPropertyValue("--line").trim() || "rgba(255,255,255,0.12)";
  const panel = getComputedStyle(document.documentElement).getPropertyValue("--panel-solid").trim() || "#121820";
  stage.innerHTML = `
    <svg class="mindmap-svg" width="${width}" height="${Math.max(120, height + 20)}" viewBox="0 0 ${width} ${Math.max(120, height + 20)}" role="img">
      ${edges
        .map(
          (e) =>
            `<path d="M${e.x1} ${e.y1} C${(e.x1 + e.x2) / 2} ${e.y1}, ${(e.x1 + e.x2) / 2} ${e.y2}, ${e.x2} ${e.y2}" fill="none" stroke="${line}" stroke-width="1.25"/>`,
        )
        .join("")}
      ${nodes
        .map(
          (n) => `
        <g class="mindmap-node" data-node-id="${n.id}" transform="translate(${n.x},${n.y})" style="cursor:${n.hasKids ? "pointer" : "default"}">
          <rect rx="8" ry="8" width="128" height="28" fill="${panel}" stroke="${line}" />
          <text x="12" y="18" fill="${ink}" font-size="12" font-family="IBM Plex Sans, PingFang SC, sans-serif">${escapeHtml(n.text).slice(0, 18)}</text>
          ${n.hasKids ? `<circle cx="118" cy="14" r="3.5" fill="${n.open ? "hsl(199 60% 55% / 0.7)" : "hsl(0 0% 100% / 0.25)"}" />` : ""}
        </g>`,
        )
        .join("")}
    </svg>
  `;
  stage.querySelectorAll(".mindmap-node").forEach((g) => {
    g.addEventListener("click", () => {
      const id = (g as HTMLElement).dataset.nodeId;
      const walk = (n: MindNode): boolean => {
        if (n.id === id) {
          if (n.children.length) n.open = !n.open;
          return true;
        }
        return n.children.some(walk);
      };
      walk(root);
      renderSvg(block, root);
    });
  });
}

function ensureChrome(block: HTMLElement, source: string) {
  block.dataset.mindmapSource = source;
  if (!block.querySelector(".mindmap-toolbar")) {
    const bar = document.createElement("div");
    bar.className = "drawio-toolbar mindmap-toolbar";
    bar.innerHTML = `
      <button type="button" class="mermaid-tool-btn icon-btn" data-mindmap-action="fold" title="折叠/展开" aria-label="折叠">${iconSvg("fold")}</button>
      <span class="drawio-badge">Mindmap</span>
      <span class="drawio-status-inline mindmap-status-inline" hidden></span>
      <span class="mermaid-toolbar-spacer"></span>
      <button type="button" class="mermaid-tool-btn icon-btn" data-mindmap-action="copy" title="复制源码" aria-label="复制">${iconSvg("copy")}</button>
      <button type="button" class="mermaid-tool-btn icon-btn" data-mindmap-action="fullscreen" title="全屏" aria-label="全屏">${iconSvg("fullscreen")}</button>
      <button type="button" class="mermaid-mode-btn is-active" data-mindmap-action="mode-view">视图</button>
      <button type="button" class="mermaid-mode-btn" data-mindmap-action="mode-source">源码</button>
    `;
    block.insertBefore(bar, block.firstChild);
  }
  if (!block.querySelector(".mindmap-viewport")) {
    const viewport = document.createElement("div");
    viewport.className = "mindmap-viewport drawio-viewport";
    const stage = document.createElement("div");
    stage.className = "mindmap-stage";
    viewport.appendChild(stage);
    block.appendChild(viewport);
  }
  const sourcePre = block.querySelector("pre.mindmap-source") as HTMLElement | null;
  if (sourcePre) {
    sourcePre.classList.add("drawio-source");
    sourcePre.hidden = true;
  }
}

function openFullscreen(block: HTMLElement) {
  document.querySelectorAll(".mindmap-fs-overlay").forEach((el) => el.remove());
  const source = block.dataset.mindmapSource || "";
  const overlay = document.createElement("div");
  overlay.className = "mermaid-fs-overlay mindmap-fs-overlay";
  overlay.innerHTML = `
    <div class="mermaid-fs-panel" role="dialog" aria-modal="true" aria-label="Mindmap fullscreen">
      <div class="mermaid-fs-toolbar">
        <span class="mermaid-fs-title">Mindmap · click nodes to expand / collapse</span>
        <div class="mermaid-fs-tools">
          <button type="button" class="mermaid-tool-btn" data-fs-close="1">关闭</button>
        </div>
      </div>
      <div class="mermaid-fs-viewport mindmap-viewport" style="overflow:auto;padding:16px">
        <div class="mindmap-stage"></div>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);
  const stageHost = overlay.querySelector(".mindmap-stage") as HTMLElement;
  const fake = document.createElement("div");
  fake.appendChild(stageHost);
  const root = parseMindmap(source);
  // mount stage back
  overlay.querySelector(".mermaid-fs-viewport")!.appendChild(stageHost);
  (overlay as any)._root = root;
  const paint = () => {
    const host = overlay as any;
    host.querySelector(".mindmap-stage") && renderSvg(overlay as any, root);
  };
  // reuse render by temporarily tagging
  (overlay as any).querySelector = overlay.querySelector.bind(overlay);
  ensureChrome(overlay as any, source);
  renderSvg(overlay as any, root);
  const close = () => overlay.remove();
  overlay.addEventListener("click", (ev) => {
    if (ev.target === overlay || (ev.target as HTMLElement).closest?.("[data-fs-close]")) close();
  });
  document.addEventListener("keydown", function onKey(ev: KeyboardEvent) {
    if (ev.key === "Escape") {
      close();
      document.removeEventListener("keydown", onKey);
    }
  });
  void paint;
}

function bindControls(root: HTMLElement) {
  if ((root as any)._nlmMindmapControls) return;
  (root as any)._nlmMindmapControls = true;
  root.addEventListener("click", async (ev) => {
    const target = ev.target as HTMLElement;
    const btn = target.closest?.("[data-mindmap-action]") as HTMLElement | null;
    const block = btn?.closest?.(".mindmap-block") as HTMLElement | null;
    if (!block || !root.contains(block)) return;
    const action = btn?.getAttribute("data-mindmap-action");
    if (!btn || !action) return;
    const source = block.dataset.mindmapSource || "";
    if (action === "fold") {
      block.classList.toggle("is-collapsed");
      return;
    }
    if (action === "copy") {
      try {
        await navigator.clipboard.writeText(source);
        setStatus(block, "Copied", false);
        setTimeout(() => setStatus(block, ""), 900);
      } catch {
        setStatus(block, "Copy failed", true);
      }
      return;
    }
    if (action === "fullscreen") {
      openFullscreen(block);
      return;
    }
    if (action === "mode-source") {
      const vp = block.querySelector(".mindmap-viewport") as HTMLElement | null;
      const src = block.querySelector("pre.mindmap-source") as HTMLElement | null;
      if (vp) vp.hidden = true;
      if (src) {
        src.hidden = false;
        src.classList.add("is-visible");
      }
      block.querySelectorAll(".mermaid-mode-btn").forEach((b) => {
        b.classList.toggle("is-active", b.getAttribute("data-mindmap-action") === "mode-source");
      });
      return;
    }
    if (action === "mode-view") {
      const vp = block.querySelector(".mindmap-viewport") as HTMLElement | null;
      const src = block.querySelector("pre.mindmap-source") as HTMLElement | null;
      if (vp) vp.hidden = false;
      if (src) {
        src.hidden = true;
        src.classList.remove("is-visible");
      }
      block.querySelectorAll(".mermaid-mode-btn").forEach((b) => {
        b.classList.toggle("is-active", b.getAttribute("data-mindmap-action") === "mode-view");
      });
    }
  });
}

export async function renderMindmapIn(root: HTMLElement | null) {
  if (!root) return;
  bindControls(root);
  const blocks = Array.from(root.querySelectorAll(".mindmap-block")) as HTMLElement[];
  for (const block of blocks) {
    if (block.getAttribute("data-processed") === "ok") continue;
    const sourcePre = block.querySelector("pre.mindmap-source");
    const source = (sourcePre?.textContent || block.dataset.mindmapSource || "").trim();
    if (!source) continue;
    try {
      ensureChrome(block, source);
      const tree = parseMindmap(source);
      (block as any)._nlmMindRoot = tree;
      renderSvg(block, tree);
      block.setAttribute("data-processed", "ok");
      setStatus(block, "");
    } catch (err: any) {
      block.setAttribute("data-processed", "error");
      setStatus(block, err?.message || String(err), true);
    }
  }
}
