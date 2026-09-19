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
};

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
    const body = String(page.content || "").trim();
    return {
      title: page.title || cite.slug,
      snippet: body.slice(0, 420),
      heading: "",
      source: `wiki:${page.slug || cite.slug}`,
    };
  }
  if (!cite.slug) {
    throw new Error("missing cite target");
  }
  try {
    const doc = await getKnowledgeDoc(cite.slug, true);
    const chunks = doc.chunks || [];
    const hit =
      cite.chunkIndex != null
        ? chunks.find((chunk) => chunk.chunk_index === cite.chunkIndex)
        : undefined;
    const snippet = String(hit?.content || doc.content || doc.snippet || "").trim();
    return {
      title: doc.title || cite.slug,
      snippet: snippet.slice(0, 420),
      heading: String(hit?.heading || hit?.context_header || ""),
      source: String(doc.source_uri || doc.source || cite.slug),
    };
  } catch {
    const remote = await getWeknoraKnowledge(cite.slug);
    if (remote.ok === false || remote.error) {
      throw new Error(String(remote.error || "原文不可用"));
    }
    const body = String(remote.content || "").trim();
    return {
      title: remote.title || cite.slug,
      snippet: body.slice(0, 420),
      heading: "",
      source: String(remote.id || cite.slug),
    };
  }
}
