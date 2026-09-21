import { getKnowledgeDoc, getWikiPage, getWeknoraKnowledge } from "@/api/endpoints";
import {
  DEFAULT_LOCAL_KB_ID,
  knowledgePath,
  parseKnowledgeLocation,
  type KnowledgeSection,
} from "@/lib/knowledgeScope";

export type KnowledgeCite = {
  kbId: string;
  section: KnowledgeSection;
  slug: string;
  chunkIndex: number | null;
  kind: "doc" | "wiki" | "graph";
  href: string;
};

export type KnowledgeCitePreview = {
  title: string;
  snippet: string;
  heading: string;
  source: string;
  matched: boolean;
};

export const CITE_SNIPPET_MISSING = "未定位到片段";

type CiteChunkLike = {
  chunk_index?: number;
  chunk_type?: string;
  content?: string;
  heading?: string;
  context_header?: string;
};

export function snippetFromChunks(
  chunks: CiteChunkLike[] | undefined,
  chunkIndex: number | null,
): { snippet: string; heading: string; matched: boolean } {
  const list = Array.isArray(chunks) ? chunks : [];
  if (chunkIndex != null) {
    const hit = list.find((chunk) => chunk.chunk_index === chunkIndex);
    const text = String(hit?.content || "").trim();
    if (text) {
      return {
        snippet: text.slice(0, 420),
        heading: String(hit?.heading || hit?.context_header || ""),
        matched: true,
      };
    }
    return { snippet: CITE_SNIPPET_MISSING, heading: "", matched: false };
  }
  const readable =
    list.find((chunk) => (chunk.chunk_type || "text") !== "parent" && String(chunk.content || "").trim()) ||
    list.find((chunk) => String(chunk.content || "").trim());
  if (readable) {
    return {
      snippet: String(readable.content || "").trim().slice(0, 420),
      heading: String(readable.heading || readable.context_header || ""),
      matched: true,
    };
  }
  return { snippet: CITE_SNIPPET_MISSING, heading: "", matched: false };
}

export function parseCiteChunkHash(hash: string): number | null {
  const m = /^#?c(\d+)$/i.exec(String(hash || "").trim());
  return m ? Number(m[1]) : null;
}

export function knowledgeHrefParts(
  href: string,
): { pathname: string; search: string; hash: string } | null {
  const raw = String(href || "").trim();
  if (!raw || /^(mailto:|javascript:)/i.test(raw)) return null;
  try {
    const u = new URL(raw, "http://nlm.local");
    if (!u.pathname.startsWith("/knowledge")) return null;
    return { pathname: u.pathname, search: u.search, hash: u.hash };
  } catch {
    return null;
  }
}

export function isKnowledgeCiteHref(href: string): boolean {
  return knowledgeHrefParts(href) != null;
}

export function parseKnowledgeCiteHref(href: string): KnowledgeCite | null {
  const parts = knowledgeHrefParts(href);
  if (!parts) return null;
  const loc = parseKnowledgeLocation(parts.pathname, parts.search);
  if (!loc) return null;
  const kind = loc.section === "wiki" ? "wiki" : loc.section === "graph" ? "graph" : "doc";
  const chunkIndex = parseCiteChunkHash(parts.hash);
  const hrefNorm =
    knowledgePath(loc.kbId, loc.section, loc.slug || undefined) +
    (chunkIndex != null ? `#c${chunkIndex}` : "");
  return {
    kbId: loc.kbId,
    section: loc.section,
    slug: loc.slug,
    chunkIndex,
    kind,
    href: hrefNorm,
  };
}

export function parseKnowledgeCiteToken(text: string, fallbackKbId = ""): KnowledgeCite | null {
  const raw = String(text || "").trim();
  const kb = fallbackKbId || DEFAULT_LOCAL_KB_ID;
  if (/^wiki:[^\s`]+$/i.test(raw)) {
    const slug = raw.slice(5);
    return {
      kbId: kb,
      section: "wiki",
      slug,
      chunkIndex: null,
      kind: "wiki",
      href: knowledgePath(kb, "wiki", slug),
    };
  }
  if (/^doc:[^\s`]+$/i.test(raw)) {
    const docId = raw.slice(4);
    return {
      kbId: kb,
      section: "docs",
      slug: docId,
      chunkIndex: null,
      kind: "doc",
      href: knowledgePath(kb, "docs", docId),
    };
  }
  return null;
}

export async function loadKnowledgeCitePreview(cite: KnowledgeCite): Promise<KnowledgeCitePreview> {
  if (cite.section === "wiki" && cite.slug) {
    const page = await getWikiPage(cite.slug, cite.kbId);
    const fromChunks = snippetFromChunks(page.chunks, cite.chunkIndex);
    if (cite.chunkIndex != null) {
      return {
        title: page.title || cite.slug,
        snippet: fromChunks.snippet,
        heading: fromChunks.heading,
        source: `wiki:${page.slug || cite.slug}`,
        matched: fromChunks.matched,
      };
    }
    const body = String(page.content || "").trim();
    if (fromChunks.matched) {
      return {
        title: page.title || cite.slug,
        snippet: fromChunks.snippet,
        heading: fromChunks.heading,
        source: `wiki:${page.slug || cite.slug}`,
        matched: true,
      };
    }
    if (body) {
      return {
        title: page.title || cite.slug,
        snippet: body.slice(0, 420),
        heading: "",
        source: `wiki:${page.slug || cite.slug}`,
        matched: true,
      };
    }
    return {
      title: page.title || cite.slug,
      snippet: CITE_SNIPPET_MISSING,
      heading: "",
      source: `wiki:${page.slug || cite.slug}`,
      matched: false,
    };
  }
  if (!cite.slug) {
    throw new Error("missing cite target");
  }
  try {
    const doc = await getKnowledgeDoc(cite.slug, true);
    const picked = snippetFromChunks(doc.chunks, cite.chunkIndex);
    return {
      title: doc.title || cite.slug,
      snippet: picked.snippet,
      heading: picked.heading,
      source: String(doc.source_uri || doc.source || cite.slug),
      matched: picked.matched,
    };
  } catch {
    const remote = await getWeknoraKnowledge(cite.slug);
    if (remote.ok === false || remote.error) {
      throw new Error(String(remote.error || "原文不可用"));
    }
    if (cite.chunkIndex != null) {
      return {
        title: remote.title || cite.slug,
        snippet: CITE_SNIPPET_MISSING,
        heading: "",
        source: String(remote.id || cite.slug),
        matched: false,
      };
    }
    const body = String(remote.content || "").trim();
    return {
      title: remote.title || cite.slug,
      snippet: body ? body.slice(0, 420) : CITE_SNIPPET_MISSING,
      heading: "",
      source: String(remote.id || cite.slug),
      matched: Boolean(body),
    };
  }
}
