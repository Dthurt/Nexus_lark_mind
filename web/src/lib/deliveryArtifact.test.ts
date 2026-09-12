import { describe, expect, it } from "vitest";

import {
  buildDeliveryMarkdown,
  extractDiagramFences,
  isMutationTool,
  planTitleFromMarkdown,
  summarizeMutationCalls,
  summarizeMutationDetail,
} from "@/lib/deliveryArtifact";

describe("deliveryArtifact", () => {
  it("extracts mermaid and drawio fences", () => {
    const md = `# Plan\n\n\`\`\`mermaid\ngraph TD\nA-->B\n\`\`\`\n\n\`\`\`drawio\n<mxfile/>\n\`\`\``;
    const fences = extractDiagramFences(md);
    expect(fences).toHaveLength(2);
    expect(fences[0].lang).toBe("mermaid");
    expect(fences[1].lang).toBe("drawio");
  });

  it("builds markdown with plan + empty changes", () => {
    const out = buildDeliveryMarkdown({
      plan: "# Feature X\n\n```mermaid\ngraph TD\nA-->B\n```",
      sessionId: "s1",
      callId: "c1",
      acceptedAt: "2026-01-01T00:00:00.000Z",
      workspacePath: ".nlm/deliveries/Delivery-Feature_X.md",
    });
    expect(out).toContain("# Delivery · Feature X");
    expect(out).toContain("## Plan");
    expect(out).toContain("## Diagrams");
    expect(out).toContain("```mermaid");
    expect(out).toContain(".nlm/deliveries/");
    expect(out).toContain("no write/edit tools yet");
  });

  it("summarizes mutation tools with detail", () => {
    expect(isMutationTool("write_file")).toBe(true);
    expect(isMutationTool("glob")).toBe(false);
    const detail = summarizeMutationDetail(
      "edit_file",
      { path: "a.ts", old_string: "foo\nbar", new_string: "baz" },
      { replacements: 1 },
    );
    expect(detail).toContain("a.ts");
    expect(detail).toContain("1× replace");
    expect(detail).toContain("2→1 lines");

    const lines = summarizeMutationCalls([
      {
        tool_name: "write_file",
        success: true,
        duration_ms: 12,
        arguments: { path: "a.ts", content: "hello\nworld" },
        result: { bytes: 11, created: true },
      },
      { tool_name: "glob", success: true },
    ]);
    expect(lines).toHaveLength(1);
    expect(lines[0]).toContain("write_file");
    expect(lines[0]).toContain("a.ts");
    expect(lines[0]).toContain("created");
  });

  it("reads title from heading", () => {
    expect(planTitleFromMarkdown("# Hello\nbody")).toBe("Hello");
  });
});
