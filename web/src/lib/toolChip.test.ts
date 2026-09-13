import { describe, expect, it } from "vitest";

import {
  formatToolDurationMs,
  oneLinePreview,
  shouldAutoExpandTool,
  shortToolName,
} from "@/lib/toolChip";

describe("toolChip helpers", () => {
  it("shortens workspace / cli tool names", () => {
    expect(shortToolName("builtin_workspace_run_shell")).toBe("run_shell");
    expect(shortToolName("cli_web_search")).toBe("web_search");
    expect(shortToolName("pkg.tool")).toBe("tool");
  });

  it("formats duration", () => {
    expect(formatToolDurationMs(12.34)).toBe("12.3 ms");
    expect(formatToolDurationMs(1500)).toBe("1.5s");
    expect(formatToolDurationMs(null)).toBe("");
  });

  it("auto-expands running / failed / highlighted", () => {
    expect(shouldAutoExpandTool({ status: "done" })).toBe(false);
    expect(shouldAutoExpandTool({ status: "running" })).toBe(true);
    expect(shouldAutoExpandTool({ status: "failed" })).toBe(true);
    expect(shouldAutoExpandTool({ status: "done", highlighted: true })).toBe(true);
    expect(shouldAutoExpandTool({ status: "done", forcedOpen: true })).toBe(true);
  });

  it("oneLinePreview collapses whitespace", () => {
    expect(oneLinePreview({ a: 1 }, 20)).toContain("a");
    expect(oneLinePreview("hello\nworld", 20)).toBe("hello world");
  });
});
