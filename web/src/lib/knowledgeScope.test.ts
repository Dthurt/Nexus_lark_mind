import { describe, expect, it } from "vitest";

import { composerKbPlaceholder, kbScopeLabel, LOCAL_KB_ID, canonicalKbId, knowledgePath, parseKnowledgeLocation, parseKnowledgePath, sameKnowledgeId } from "@/lib/knowledgeScope";

describe("knowledgeScope", () => {
  it("labels empty id as local KB", () => {
    expect(LOCAL_KB_ID).toBe("");
    expect(kbScopeLabel("")).toBe("本地知识库");
    expect(kbScopeLabel(undefined)).toBe("本地知识库");
  });

  it("prefers WeKnora name over raw id", () => {
    expect(kbScopeLabel("kb-9", "产品文档")).toBe("产品文档");
    expect(kbScopeLabel("kb-9")).toBe("kb-9");
  });

  it("builds composer placeholder from the bound KB", () => {
    expect(composerKbPlaceholder("", "")).toContain("本地知识库");
    expect(composerKbPlaceholder("kb-1", "产品文档")).toContain("产品文档");
  });

  it("encodes nested knowledge paths including colon ids", () => {
    expect(knowledgePath("")).toBe("/knowledge/local%3Adefault");
    expect(knowledgePath("local:default")).toBe("/knowledge/local%3Adefault");
    expect(knowledgePath("local:a9a4eb2093")).toBe("/knowledge/local%3Aa9a4eb2093");
    expect(parseKnowledgePath("/knowledge")).toBe("");
    expect(parseKnowledgePath("/knowledge/local%3Adefault")).toBe("local:default");
    expect(parseKnowledgePath("/knowledge/local:a9a4eb2093")).toBe("local:a9a4eb2093");
    expect(parseKnowledgePath("/knowledge/local%3Adefault/docs/abc")).toBe("local:default");
    expect(knowledgePath("local:default", "wiki")).toBe("/knowledge/local%3Adefault/wiki");
    expect(knowledgePath("local:default", "wiki", "alpha")).toBe("/knowledge/local%3Adefault/wiki/alpha");
    expect(knowledgePath("local:default", "graph")).toBe("/knowledge/local%3Adefault/graph");
    expect(knowledgePath("local:default", "docs", "file_abc")).toBe(
      "/knowledge/local%3Adefault/docs/file_abc",
    );
    expect(parseKnowledgeLocation("/knowledge/local%3Adefault/docs/file_abc")?.slug).toBe("file_abc");
    expect(parseKnowledgeLocation("/knowledge/local%3Adefault/docs/file_abc")?.section).toBe("docs");
    expect(parseKnowledgeLocation("/knowledge/local%3Adefault", "?doc=file_abc")?.slug).toBe(
      "file_abc",
    );
    expect(parseKnowledgeLocation("/knowledge/local%3Adefault/wiki/hello")?.section).toBe("wiki");
    expect(parseKnowledgeLocation("/knowledge/local%3Adefault/wiki/hello")?.slug).toBe("hello");
    expect(parseKnowledgeLocation("/knowledge/local%3Adefault/graph")?.section).toBe("graph");
    expect(parseKnowledgePath("/")).toBeNull();
    expect(sameKnowledgeId("", "local:default")).toBe(true);
    expect(sameKnowledgeId("local:legal", "local:legal")).toBe(true);
    expect(sameKnowledgeId("local:legal", "")).toBe(false);
    expect(canonicalKbId("")).toBe("local:default");
    expect(canonicalKbId("local:default")).toBe("local:default");
  });
});
