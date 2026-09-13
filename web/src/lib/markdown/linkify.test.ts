import { describe, expect, it } from "vitest";

import { escapeHtml, linkifyPlainText } from "./linkify";

describe("linkifyPlainText", () => {
  it("wraps https urls", () => {
    const html = linkifyPlainText("see https://example.com/path and done");
    expect(html).toContain('<a href="https://example.com/path"');
    expect(html).toContain("target=\"_blank\"");
  });

  it("promotes www to https", () => {
    const html = linkifyPlainText("open www.github.com/foo");
    expect(html).toContain('href="https://www.github.com/foo"');
  });

  it("escapes html", () => {
    expect(escapeHtml("<script>")).toBe("&lt;script&gt;");
  });
});
