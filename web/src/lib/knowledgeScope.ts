export const LOCAL_KB_ID = "";
export const DEFAULT_LOCAL_KB_ID = "local:default";
export const ALL_LOCAL_KB_ID = "local:all";

export type KnowledgeScopeOption = {
  id: string;
  name: string;
  source: "local" | "weknora";
  docCount?: number | null;
};

export function isLocalKbId(id?: string): boolean {
  const kid = String(id || "").trim();
  return !kid || kid.startsWith("local:");
}

export function kbScopeLabel(id?: string, name?: string): string {
  const kid = String(id || "").trim();
  const label = String(name || "").trim();
  if (!kid || kid === DEFAULT_LOCAL_KB_ID) return label || "本地知识库";
  if (kid.startsWith("local:")) return label || kid.slice("local:".length);
  return label || kid;
}

export function composerKbPlaceholder(id?: string, name?: string): string {
  return `基于「${kbScopeLabel(id, name)}」提问 · @ 附加文件 · Enter 发送`;
}

export function canonicalKbId(id?: string): string {
  const kid = String(id || "").trim();
  return !kid || kid === DEFAULT_LOCAL_KB_ID ? DEFAULT_LOCAL_KB_ID : kid;
}

export function sameKnowledgeId(a?: string, b?: string): boolean {
  return canonicalKbId(a) === canonicalKbId(b);
}

export type KnowledgeSection = "docs" | "wiki" | "graph";

export type KnowledgeLocation = {
  kbId: string;
  section: KnowledgeSection;
  slug: string;
};

function decodePathPart(raw: string): string {
  try {
    return decodeURIComponent(raw);
  } catch {
    return raw;
  }
}

export function knowledgePath(
  kbId?: string,
  section: KnowledgeSection = "docs",
  slug?: string,
): string {
  const base = `/knowledge/${encodeURIComponent(canonicalKbId(kbId))}`;
  if (section === "wiki") {
    return slug ? `${base}/wiki/${encodeURIComponent(slug)}` : `${base}/wiki`;
  }
  if (section === "graph") return `${base}/graph`;
  if (section === "docs" && slug) {
    return `${base}/docs/${encodeURIComponent(slug)}`;
  }
  return base;
}

export function parseKnowledgeLocation(pathname: string, search = ""): KnowledgeLocation | null {
  const path = String(pathname || "");
  if (path === "/knowledge" || path === "/knowledge/") {
    return withDocQuery({ kbId: "", section: "docs", slug: "" }, search);
  }
  if (!path.startsWith("/knowledge/")) return null;
  const parts = path.slice("/knowledge/".length).split("/").filter(Boolean);
  const kbId = decodePathPart(parts[0] || "");
  const sectionRaw = parts[1] || "";
  if (sectionRaw === "wiki") {
    return { kbId, section: "wiki", slug: decodePathPart(parts[2] || "") };
  }
  if (sectionRaw === "graph") {
    return { kbId, section: "graph", slug: "" };
  }
  if (sectionRaw === "docs") {
    return { kbId, section: "docs", slug: decodePathPart(parts[2] || "") };
  }
  return withDocQuery({ kbId, section: "docs", slug: "" }, search);
}

function withDocQuery(loc: KnowledgeLocation, search: string): KnowledgeLocation {
  if (loc.section !== "docs" || loc.slug) return loc;
  const raw = String(search || "");
  if (!raw) return loc;
  const q = new URLSearchParams(raw.startsWith("?") ? raw.slice(1) : raw);
  const doc = (q.get("doc") || "").trim();
  return doc ? { ...loc, slug: doc } : loc;
}

export function parseKnowledgePath(pathname: string): string | null {
  const loc = parseKnowledgeLocation(pathname);
  return loc ? loc.kbId : null;
}

export function isKnowledgeRoute(pathname: string): boolean {
  const path = String(pathname || "");
  return path === "/knowledge" || path.startsWith("/knowledge/");
}
