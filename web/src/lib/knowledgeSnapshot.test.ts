import { describe, expect, it } from "vitest";

import { highlightPlainText, locateTextMatch, normalizeSnapshot } from "@/lib/knowledgeSnapshot";

describe("knowledgeSnapshot", () => {
  it("locates the earliest token in original text", () => {
    const loc = locateTextMatch("Cats purr and nap in sunbeams.", "feline", ["purr", "sun"]);
    expect(loc?.text).toBe("purr");
    expect(loc?.start).toBe("Cats ".length);
  });

  it("highlights a query inside a chunk", () => {
    const parts = highlightPlainText("alpha marker in default library", "marker");
    expect(parts.prefix).toBe("alpha ");
    expect(parts.highlight).toBe("marker");
    expect(parts.suffix).toContain("in default");
  });

  it("normalizes a server snapshot for 原文对比", () => {
    const snap = normalizeSnapshot({
      prefix: "…the ",
      highlight: "vector",
      suffix: " store…",
      match_kind: "keyword",
    });
    expect(snap.snippet).toContain("vector");
    expect(snap.match_kind).toBe("keyword");
  });
});
