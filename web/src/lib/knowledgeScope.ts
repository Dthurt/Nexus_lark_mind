export const LOCAL_KB_ID = "";
export const DEFAULT_LOCAL_KB_ID = "local:default";

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

export function knowledgePath(kbId?: string): string {
  return `/knowledge/${encodeURIComponent(canonicalKbId(kbId))}`;
}

export function parseKnowledgePath(pathname: string): string | null {
  const path = String(pathname || "");
  if (path === "/knowledge" || path === "/knowledge/") return "";
  if (!path.startsWith("/knowledge/")) return null;
  const raw = path.slice("/knowledge/".length).split("/").filter(Boolean)[0] || "";
  if (!raw) return "";
  try {
    return decodeURIComponent(raw);
  } catch {
    return raw;
  }
}

export function isKnowledgeRoute(pathname: string): boolean {
  const path = String(pathname || "");
  return path === "/knowledge" || path.startsWith("/knowledge/");
}
