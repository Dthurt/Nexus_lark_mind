import { describe, expect, it } from "vitest";

import { composerKbPlaceholder, kbScopeLabel, LOCAL_KB_ID } from "@/lib/knowledgeScope";

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
});
