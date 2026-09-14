import { describe, expect, it } from "vitest";

import { trajectoryPreviewText } from "./trajectoryPreview";

describe("trajectoryPreviewText", () => {
  it("strips markdown noise into one line", () => {
    const out = trajectoryPreviewText("## Hello\n\n**bold** and `code` [link](https://x)");
    expect(out).toContain("Hello");
    expect(out).toContain("bold");
    expect(out).toContain("code");
    expect(out).toContain("link");
    expect(out).not.toContain("https://");
    expect(out).not.toMatch(/\n/);
  });

  it("ellipsis when truncated", () => {
    const long = "word ".repeat(200);
    const out = trajectoryPreviewText(long);
    expect(out.endsWith("…")).toBe(true);
  });
});
