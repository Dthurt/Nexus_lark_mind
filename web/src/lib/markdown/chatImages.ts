/** Chat image gallery + lightbox (open / zoom / download / prev-next). */

function iconSvg(name: string) {
  const c =
    'width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"';
  if (name === "expand") {
    return `<svg ${c}><path d="M8 3H5a2 2 0 0 0-2 2v3"/><path d="M16 3h3a2 2 0 0 1 2 2v3"/><path d="M8 21H5a2 2 0 0 1-2-2v-3"/><path d="M16 21h3a2 2 0 0 0 2-2v-3"/></svg>`;
  }
  if (name === "download") {
    return `<svg ${c}><path d="M12 3v12"/><path d="M7 10l5 5 5-5"/><path d="M5 21h14"/></svg>`;
  }
  if (name === "external") {
    return `<svg ${c}><path d="M14 3h7v7"/><path d="M10 14L21 3"/><path d="M21 14v6a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h6"/></svg>`;
  }
  if (name === "close") {
    return `<svg ${c}><path d="M6 6l12 12M18 6L6 18"/></svg>`;
  }
  if (name === "prev") {
    return `<svg ${c}><path d="M15 6l-6 6 6 6"/></svg>`;
  }
  if (name === "next") {
    return `<svg ${c}><path d="M9 6l6 6-6 6"/></svg>`;
  }
  return "";
}

function downloadUrl(url: string, name?: string) {
  const a = document.createElement("a");
  a.href = url;
  a.download = name || `image-${Date.now()}.png`;
  a.target = "_blank";
  a.rel = "noopener noreferrer";
  document.body.appendChild(a);
  a.click();
  a.remove();
}

let lightboxEl: HTMLElement | null = null;
let lightboxState: { items: { src: string; alt: string }[]; index: number; scale: number } = {
  items: [],
  index: 0,
  scale: 1,
};

function closeLightbox() {
  if (!lightboxEl) return;
  lightboxEl.remove();
  lightboxEl = null;
  document.documentElement.classList.remove("chat-image-lb-open");
  document.removeEventListener("keydown", onLightboxKey);
}

function onLightboxKey(ev: KeyboardEvent) {
  if (!lightboxEl) return;
  if (ev.key === "Escape") closeLightbox();
  else if (ev.key === "ArrowLeft") showLightboxIndex(lightboxState.index - 1);
  else if (ev.key === "ArrowRight") showLightboxIndex(lightboxState.index + 1);
  else if (ev.key === "+" || ev.key === "=") setLightboxZoom(lightboxState.scale + 0.2);
  else if (ev.key === "-" || ev.key === "_") setLightboxZoom(lightboxState.scale - 0.2);
  else if (ev.key === "0") setLightboxZoom(1);
}

function setLightboxZoom(scale: number) {
  lightboxState.scale = Math.max(0.4, Math.min(4, scale));
  const img = lightboxEl?.querySelector?.(".chat-image-lb-img") as HTMLElement | null;
  if (img) img.style.transform = `scale(${lightboxState.scale})`;
  const label = lightboxEl?.querySelector?.("[data-lb-zoom-label]");
  if (label) label.textContent = `${Math.round(lightboxState.scale * 100)}%`;
}

function showLightboxIndex(i: number) {
  const items = lightboxState.items;
  if (!items.length) return;
  const n = ((i % items.length) + items.length) % items.length;
  lightboxState.index = n;
  lightboxState.scale = 1;
  const item = items[n];
  const img = lightboxEl!.querySelector(".chat-image-lb-img") as HTMLImageElement | null;
  const cap = lightboxEl!.querySelector(".chat-image-lb-cap");
  const counter = lightboxEl!.querySelector("[data-lb-counter]");
  if (img) {
    img.src = item.src;
    img.alt = item.alt || "";
    img.style.transform = "scale(1)";
  }
  if (cap) cap.textContent = item.alt || "";
  if (counter) counter.textContent = `${n + 1} / ${items.length}`;
}

function openLightbox(items: { src: string; alt: string }[], startIndex = 0) {
  closeLightbox();
  lightboxState = { items, index: startIndex, scale: 1 };
  const overlay = document.createElement("div");
  overlay.className = "chat-image-lb-overlay";
  overlay.innerHTML = `
    <div class="chat-image-lb-panel" role="dialog" aria-modal="true" aria-label="图片预览">
      <div class="chat-image-lb-toolbar">
        <span data-lb-counter></span>
        <span class="chat-image-lb-spacer"></span>
        <button type="button" class="chat-image-lb-btn" data-lb-zoom="-1" title="缩小">−</button>
        <span data-lb-zoom-label>100%</span>
        <button type="button" class="chat-image-lb-btn" data-lb-zoom="1" title="放大">+</button>
        <button type="button" class="chat-image-lb-btn" data-lb-action="download" title="下载">${iconSvg("download")}</button>
        <button type="button" class="chat-image-lb-btn" data-lb-action="open" title="新窗口">${iconSvg("external")}</button>
        <button type="button" class="chat-image-lb-btn" data-lb-action="close" title="关闭">${iconSvg("close")}</button>
      </div>
      <div class="chat-image-lb-stage">
        <button type="button" class="chat-image-lb-nav prev" data-lb-nav="-1" title="上一张" aria-label="上一张">${iconSvg("prev")}</button>
        <img class="chat-image-lb-img" alt="" />
        <button type="button" class="chat-image-lb-nav next" data-lb-nav="1" title="下一张" aria-label="下一张">${iconSvg("next")}</button>
      </div>
      <div class="chat-image-lb-cap"></div>
    </div>
  `;
  document.body.appendChild(overlay);
  lightboxEl = overlay;
  document.documentElement.classList.add("chat-image-lb-open");
  document.addEventListener("keydown", onLightboxKey);

  overlay.addEventListener("click", (ev) => {
    if (ev.target === overlay) closeLightbox();
    const btn = (ev.target as HTMLElement).closest?.("[data-lb-action],[data-lb-nav],[data-lb-zoom]");
    if (!btn) return;
    if (btn.hasAttribute("data-lb-action")) {
      const act = btn.getAttribute("data-lb-action");
      const cur = lightboxState.items[lightboxState.index];
      if (act === "close") closeLightbox();
      else if (act === "download" && cur) downloadUrl(cur.src, (cur.alt || "image").slice(0, 40));
      else if (act === "open" && cur) window.open(cur.src, "_blank", "noopener,noreferrer");
    } else if (btn.hasAttribute("data-lb-nav")) {
      showLightboxIndex(lightboxState.index + Number(btn.getAttribute("data-lb-nav") || 0));
    } else if (btn.hasAttribute("data-lb-zoom")) {
      setLightboxZoom(lightboxState.scale + Number(btn.getAttribute("data-lb-zoom") || 0) * 0.25);
    }
  });

  const stage = overlay.querySelector(".chat-image-lb-stage");
  stage?.addEventListener(
    "wheel",
    (ev: Event) => {
      const wev = ev as WheelEvent;
      wev.preventDefault();
      setLightboxZoom(lightboxState.scale + (wev.deltaY < 0 ? 0.12 : -0.12));
    },
    { passive: false }
  );

  showLightboxIndex(startIndex);
}

function collectGalleryItems(gallery: Element) {
  return [...gallery.querySelectorAll(".chat-image")]
    .map((fig) => {
      const img = fig.querySelector("img");
      return {
        src: img?.getAttribute("src") || "",
        alt: img?.getAttribute("alt") || fig.querySelector(".chat-image-cap")?.textContent || "",
      };
    })
    .filter((x) => x.src);
}

function wrapOne(img: HTMLImageElement) {
  if (img.closest(".chat-image") || img.closest(".mermaid-block") || img.closest(".echarts-block")) {
    return null;
  }
  const src = img.getAttribute("src") || "";
  if (!src) return null;

  const figure = document.createElement("figure");
  figure.className = "chat-image";
  const frame = document.createElement("div");
  frame.className = "chat-image-frame";
  img.parentNode!.insertBefore(figure, img);
  frame.appendChild(img);
  figure.appendChild(frame);

  img.loading = img.loading || "lazy";
  img.decoding = "async";
  img.addEventListener("error", () => {
    figure.classList.add("is-error");
    if (!figure.querySelector(".chat-image-error")) {
      const err = document.createElement("div");
      err.className = "chat-image-error";
      err.textContent = "图片加载失败";
      frame.appendChild(err);
    }
  });

  const alt = img.getAttribute("alt") || "";
  if (alt) {
    const cap = document.createElement("figcaption");
    cap.className = "chat-image-cap";
    cap.textContent = alt;
    figure.appendChild(cap);
  }

  const actions = document.createElement("div");
  actions.className = "chat-image-actions";
  actions.innerHTML = `
    <button type="button" class="chat-image-btn" data-img-action="lightbox" title="放大预览">${iconSvg("expand")}</button>
    <button type="button" class="chat-image-btn" data-img-action="open" title="新窗口打开">${iconSvg("external")}</button>
    <button type="button" class="chat-image-btn" data-img-action="download" title="下载">${iconSvg("download")}</button>
  `;
  figure.appendChild(actions);

  frame.addEventListener("click", () => {
    const gallery = figure.closest(".chat-image-gallery");
    const items = gallery ? collectGalleryItems(gallery) : [{ src, alt }];
    const idx = gallery
      ? Math.max(0, [...gallery.querySelectorAll(".chat-image")].indexOf(figure))
      : 0;
    openLightbox(items, idx);
  });

  return figure;
}

function groupConsecutive(root: HTMLElement) {
  const figures = [...root.querySelectorAll(".chat-image")].filter(
    (f) => !f.closest(".chat-image-gallery")
  );
  if (figures.length < 2) return;

  const runs: Element[][] = [];
  let run: Element[] = [figures[0]];

  const isNear = (a: Element, b: Element) => {
    if (a.parentElement === b.parentElement) return true;
    // consecutive paragraphs each holding one image
    const pa = a.parentElement;
    const pb = b.parentElement;
    if (pa && pb && pa.parentElement === pb.parentElement) {
      const kids = [...pa.parentElement!.children];
      const ia = kids.indexOf(pa);
      const ib = kids.indexOf(pb);
      if (ia >= 0 && ib === ia + 1 && pa.tagName === "P" && pb.tagName === "P") return true;
    }
    if (a.nextElementSibling === b) return true;
    return false;
  };

  for (let i = 1; i < figures.length; i += 1) {
    if (isNear(run[run.length - 1], figures[i])) run.push(figures[i]);
    else {
      runs.push(run);
      run = [figures[i]];
    }
  }
  runs.push(run);

  for (const group of runs) {
    if (group.length < 2) continue;
    const gallery = document.createElement("div");
    gallery.className = "chat-image-gallery";
    gallery.dataset.count = String(group.length);

    const head = document.createElement("div");
    head.className = "chat-image-gallery-head";
    head.innerHTML = `<span class="chat-image-gallery-label">${group.length} 张图片</span>`;
    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "chat-image-gallery-toggle";
    toggle.textContent = "收起";
    toggle.addEventListener("click", (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      const collapsed = gallery.classList.toggle("is-collapsed");
      toggle.textContent = collapsed ? "展开" : "收起";
    });
    head.appendChild(toggle);

    const body = document.createElement("div");
    body.className = "chat-image-gallery-body";

    const first = group[0];
    // If images live in consecutive <p>, hoist into gallery at the first paragraph position
    const host = first.parentElement?.tagName === "P" ? first.parentElement : first;
    host.parentNode!.insertBefore(gallery, host);
    gallery.appendChild(head);
    gallery.appendChild(body);
    group.forEach((fig) => {
      const p = fig.parentElement;
      body.appendChild(fig);
      if (p && p.tagName === "P" && !p.textContent!.trim() && !p.children.length) p.remove();
    });
  }
}

function bindGalleryActions(root: any) {
  if (!root || root._nlmChatImageActions) return;
  root._nlmChatImageActions = true;
  root.addEventListener("click", (ev: MouseEvent) => {
    const btn = (ev.target as HTMLElement).closest?.("[data-img-action]");
    const frame = (ev.target as HTMLElement).closest?.(".chat-image-frame");
    if (btn && root.contains(btn)) {
      ev.preventDefault();
      ev.stopPropagation();
      const fig = btn.closest(".chat-image");
      const img = fig?.querySelector("img");
      const src = img?.getAttribute("src") || "";
      const alt = img?.getAttribute("alt") || "";
      const act = btn.getAttribute("data-img-action");
      if (act === "lightbox") {
        const gallery = fig?.closest(".chat-image-gallery");
        const items = gallery ? collectGalleryItems(gallery) : [{ src, alt }];
        const idx = gallery ? Math.max(0, [...gallery.querySelectorAll(".chat-image")].indexOf(fig!)) : 0;
        openLightbox(items, idx);
      } else if (act === "open" && src) {
        window.open(src, "_blank", "noopener,noreferrer");
      } else if (act === "download" && src) {
        const a = document.createElement("a");
        a.href = src;
        a.download = (alt || "image").replace(/[\\/:*?"<>|]/g, "_");
        a.rel = "noopener";
        a.click();
      }
      return;
    }
    if (frame && root.contains(frame)) {
      ev.preventDefault();
      const fig = frame.closest(".chat-image");
      const img = fig?.querySelector("img");
      const src = img?.getAttribute("src") || "";
      const alt = img?.getAttribute("alt") || "";
      if (!src) return;
      const gallery = fig?.closest(".chat-image-gallery");
      const items = gallery ? collectGalleryItems(gallery) : [{ src, alt }];
      const idx = gallery ? Math.max(0, [...gallery.querySelectorAll(".chat-image")].indexOf(fig!)) : 0;
      openLightbox(items, idx);
    }
  });
}

/** Wrap markdown images for chat display (generated / searched images). */
export function enhanceChatImages(root: HTMLElement | null) {
  if (!root) return;
  bindGalleryActions(root);
  root.querySelectorAll("img").forEach((img) => {
    wrapOne(img as HTMLImageElement);
  });
  groupConsecutive(root);
}
