import { describe, expect, it } from "vitest";

import { rewriteWikiLinks, slugifyWiki } from "@/lib/wikiLinks";

describe("wikiLinks", () => {
  it("slugifies titles and rewrites wiki links", () => {
    expect(slugifyWiki("Hello World")).toBe("hello-world");
    const md = rewriteWikiLinks("See [[Other]] and [[doc:abc|原文]]", "local:default");
    expect(md).toContain("/knowledge/local%3Adefault/wiki/other");
    expect(md).toContain("/knowledge/local%3Adefault/docs/abc");
  });
});
