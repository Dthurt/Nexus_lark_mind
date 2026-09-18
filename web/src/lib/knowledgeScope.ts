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
