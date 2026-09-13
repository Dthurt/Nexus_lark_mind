import { describe, expect, it } from "vitest";

import {
  addContextRef,
  applyMentionReplacement,
  detectMentionAt,
} from "@/lib/contextRefs";

describe("contextRefs", () => {
  it("detects @query at caret", () => {
    expect(detectMentionAt("see @src", 8)).toEqual({ start: 4, query: "src" });
    expect(detectMentionAt("hello", 5)).toBeNull();
  });

  it("dedupes refs", () => {
    const a = addContextRef([], { path: "a.ts", kind: "file" });
    const b = addContextRef(a, { path: "a.ts", kind: "file" });
    expect(b).toHaveLength(1);
  });

  it("applies mention replacement", () => {
    const { text } = applyMentionReplacement("look @fo", 5, 8, "foo.ts");
    expect(text).toContain("@foo.ts");
  });
});
