import { describe, expect, it } from "vitest";

import {
  isKnowledgeCiteHref,
  parseCiteChunkHash,
  parseKnowledgeCiteHref,
  parseKnowledgeCiteToken,
} from "@/lib/kbCite";

describe("kbCite", () => {
  it("parses in-app doc and wiki cite hrefs with chunk hash", () => {
    const doc = parseKnowledgeCiteHref("/knowledge/local%3Adefault/docs/file_abc#c2");
    expect(doc?.kind).toBe("doc");
    expect(doc?.slug).toBe("file_abc");
    expect(doc?.chunkIndex).toBe(2);
    expect(doc?.href).toContain("/docs/file_abc");
    expect(doc?.href).toContain("#c2");

    const wiki = parseKnowledgeCiteHref("/knowledge/local%3Adefault/wiki/_index");
    expect(wiki?.kind).toBe("wiki");
    expect(wiki?.slug).toBe("_index");
    expect(wiki?.chunkIndex).toBeNull();
  });

  it("accepts ?doc= alias and token forms", () => {
    const aliased = parseKnowledgeCiteHref("/knowledge/local%3Adefault?doc=file_abc");
    expect(aliased?.slug).toBe("file_abc");
    expect(aliased?.section).toBe("docs");
    expect(parseKnowledgeCiteToken("doc:file_abc", "local:legal")?.href).toContain(
      "/knowledge/local%3Alegal/docs/file_abc",
    );
    expect(parseKnowledgeCiteToken("wiki:_index")?.section).toBe("wiki");
    expect(isKnowledgeCiteHref("https://example.com/other")).toBe(false);
    expect(parseCiteChunkHash("#c12")).toBe(12);
  });
});
