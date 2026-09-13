/** Composer @ context references (Cursor-like). */

export type ContextRefKind = "file" | "dir";

export type ContextRef = {
  path: string;
  kind: ContextRefKind;
  label?: string;
};

export function normalizeContextPath(path: string): string {
  return String(path || "")
    .trim()
    .replace(/\\/g, "/")
    .replace(/^\.\//, "");
}

export function sameContextRef(a: ContextRef, b: ContextRef): boolean {
  return normalizeContextPath(a.path) === normalizeContextPath(b.path) && a.kind === b.kind;
}

export function addContextRef(list: ContextRef[], ref: ContextRef): ContextRef[] {
  const next: ContextRef = {
    path: normalizeContextPath(ref.path),
    kind: ref.kind === "dir" ? "dir" : "file",
    label: ref.label,
  };
  if (!next.path) return list;
  if (list.some((x) => sameContextRef(x, next))) return list;
  return [...list, next].slice(0, 12);
}

/** Detect trailing @query at caret for mention popover. */
export function detectMentionAt(
  text: string,
  caret: number,
): { start: number; query: string } | null {
  const before = text.slice(0, Math.max(0, caret));
  const m = before.match(/(^|[\s\n])@([^\s@]*)$/);
  if (!m) return null;
  const query = m[2] || "";
  const start = before.length - query.length - 1;
  return { start, query };
}

export function applyMentionReplacement(
  text: string,
  start: number,
  caret: number,
  insertPath: string,
): { text: string; caret: number } {
  const before = text.slice(0, start);
  const after = text.slice(caret);
  // Chips carry the ref; leave a short @token in text for readability
  const token = `@${insertPath}`;
  const next = `${before}${token}${after.startsWith(" ") || after.startsWith("\n") ? "" : " "}${after}`;
  const newCaret = before.length + token.length + 1;
  return { text: next, caret: newCaret };
}
