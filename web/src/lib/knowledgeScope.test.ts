import { describe, expect, it } from "vitest";

import { composerKbPlaceholder, kbScopeLabel, LOCAL_KB_ID, knowledgePath, parseKnowledgePath, sameKnowledgeId } from "@/lib/knowledgeScope";

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
    expect(parseKnowledgePath("/")).toBeNull();
    expect(sameKnowledgeId("", "local:default")).toBe(true);
    expect(sameKnowledgeId("local:legal", "local:legal")).toBe(true);
    expect(sameKnowledgeId("local:legal", "")).toBe(false);
  });
});
