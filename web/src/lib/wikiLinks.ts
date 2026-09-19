import { knowledgePath } from "@/lib/knowledgeScope";

export function slugifyWiki(title: string): string {
  const s = String(title || "")
    .trim()
    .toLowerCase()
    .replace(/^doc:/, "")
    .replace(/[[\]#?&=\s]+/g, "-")
    .replace(/[^a-z0-9\u4e00-\u9fff\-_.]+/g, "")
    .replace(/-{2,}/g, "-")
    .replace(/^[-._]+|[-._]+$/g, "");
  return (s || "page").slice(0, 80);
}

export function rewriteWikiLinks(md: string, kbId: string): string {
  return String(md || "").replace(/\[\[([^[\]]+)\]\]/g, (_m, inner: string) => {
    const raw = String(inner || "").trim();
    const pipe = raw.indexOf("|");
    const target = (pipe >= 0 ? raw.slice(0, pipe) : raw).trim();
    const label = (pipe >= 0 ? raw.slice(pipe + 1) : raw).trim() || target;
    if (target.toLowerCase().startsWith("doc:")) {
      const docId = target.slice(4);
      return `[${label}](${knowledgePath(kbId, "docs", docId)})`;
    }
    return `[${label}](${knowledgePath(kbId, "wiki", slugifyWiki(target))})`;
  });
}
