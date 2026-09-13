/**
 * Autolink bare URLs / www hosts in plain text (outside existing markdown links).
 * Used for user bubbles and as a safety net after GFM render.
 */

const URL_RE =
  /((?:https?:\/\/|www\.)[^\s<>()\[\]{}"']+[^\s<>()\[\]{}"'.,!?;:])/gi;

export function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function normalizeHref(raw: string): string {
  const t = raw.trim();
  if (/^www\./i.test(t)) return `https://${t}`;
  return t;
}

/** Escape + wrap bare URLs as <a> for plain-text messages. */
export function linkifyPlainText(text: string): string {
  if (!text) return "";
  const parts: string[] = [];
  let last = 0;
  const re = new RegExp(URL_RE.source, URL_RE.flags);
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    const start = m.index;
    const matched = m[0];
    if (start > last) parts.push(escapeHtml(text.slice(last, start)));
    const href = normalizeHref(matched);
    parts.push(
      `<a href="${escapeHtml(href)}" target="_blank" rel="noopener noreferrer">${escapeHtml(matched)}</a>`,
    );
    last = start + matched.length;
  }
  if (last < text.length) parts.push(escapeHtml(text.slice(last)));
  return parts.join("").replace(/\n/g, "<br/>");
}

/** Walk text nodes under root and wrap bare URLs (skip <a>/<code>/<pre>). */
export function linkifyElement(root: HTMLElement | null) {
  if (!root) return;
  const skip = new Set(["A", "CODE", "PRE", "SCRIPT", "STYLE"]);
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const nodes: Text[] = [];
  let node = walker.nextNode();
  while (node) {
    const parent = node.parentElement;
    if (parent && !skip.has(parent.tagName) && !parent.closest("a, code, pre")) {
      if (URL_RE.test(node.textContent || "")) nodes.push(node as Text);
      URL_RE.lastIndex = 0;
    }
    node = walker.nextNode();
  }
  for (const textNode of nodes) {
    const raw = textNode.textContent || "";
    if (!URL_RE.test(raw)) continue;
    URL_RE.lastIndex = 0;
    const span = document.createElement("span");
    span.innerHTML = linkifyPlainText(raw);
    textNode.parentNode?.replaceChild(span, textNode);
  }
}
