export const LOCAL_KB_ID = "";

export type KnowledgeScopeOption = {
  id: string;
  name: string;
  source: "local" | "weknora";
  docCount?: number | null;
};

export function kbScopeLabel(id?: string, name?: string): string {
  const kid = String(id || "").trim();
  if (!kid) return "本地知识库";
  return String(name || "").trim() || kid;
}

export function composerKbPlaceholder(id?: string, name?: string): string {
  return `基于「${kbScopeLabel(id, name)}」提问 · @ 附加文件 · Enter 发送`;
}
