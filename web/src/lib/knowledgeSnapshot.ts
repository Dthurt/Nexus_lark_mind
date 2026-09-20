export type TextSnapshot = {
  snippet?: string;
  prefix?: string;
  highlight?: string;
  suffix?: string;
  match_start?: number | null;
  match_end?: number | null;
  match_text?: string;
  match_kind?: "keyword" | "semantic" | "none" | string;
};

export function locateTextMatch(
  content: string,
  query = "",
  tokens: string[] = [],
): { start: number; end: number; text: string } | null {
  const text = String(content || "");
  if (!text) return null;
  const candidates: string[] = [];
  for (const token of tokens) {
    const s = String(token || "").trim();
    if (s && !candidates.includes(s)) candidates.push(s);
  }
  const q = String(query || "").trim();
  if (q && !candidates.includes(q)) candidates.push(q);
  const lower = text.toLowerCase();
  let best: { start: number; end: number; text: string } | null = null;
  for (const c of candidates) {
    const i = lower.indexOf(c.toLowerCase());
    if (i < 0) continue;
    const hit = text.slice(i, i + c.length);
    if (!best || i < best.start || (i === best.start && c.length > best.end - best.start)) {
      best = { start: i, end: i + c.length, text: hit };
    }
  }
  return best;
}

export function normalizeSnapshot(
  snap?: TextSnapshot | null,
  fallback = "",
): TextSnapshot {
  if (snap && (snap.prefix || snap.highlight || snap.suffix || snap.snippet)) {
    return {
      prefix: snap.prefix || "",
      highlight: snap.highlight || snap.match_text || "",
      suffix: snap.suffix || "",
      snippet: snap.snippet || `${snap.prefix || ""}${snap.highlight || ""}${snap.suffix || ""}`,
      match_start: snap.match_start ?? -1,
      match_end: snap.match_end ?? -1,
      match_text: snap.match_text || snap.highlight || "",
      match_kind: snap.match_kind || (snap.highlight ? "keyword" : "semantic"),
    };
  }
  return {
    prefix: fallback,
    highlight: "",
    suffix: "",
    snippet: fallback,
    match_start: -1,
    match_end: -1,
    match_text: "",
    match_kind: "semantic",
  };
}

export function highlightPlainText(
  content: string,
  query = "",
  tokens: string[] = [],
): { prefix: string; highlight: string; suffix: string } {
  const loc = locateTextMatch(content, query, tokens);
  if (!loc) {
    return { prefix: content, highlight: "", suffix: "" };
  }
  return {
    prefix: content.slice(0, loc.start),
    highlight: loc.text,
    suffix: content.slice(loc.end),
  };
}
