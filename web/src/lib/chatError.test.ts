import { describe, expect, it } from "vitest";

import {
  errorFlagsFromMessage,
  formatStreamErrorText,
  isPersistedErrorMessage,
} from "@/lib/chatError";

describe("chatError", () => {
  it("detects persisted session error messages", () => {
    expect(isPersistedErrorMessage({ role: "assistant", content: "hi" })).toBe(false);
    expect(
      isPersistedErrorMessage({
        role: "assistant",
        content: "错误：deepseek-self stream HTTP 400",
        metadata: { kind: "error", error: "deepseek-self stream HTTP 400" },
      }),
    ).toBe(true);
  });

  it("formats stream errors the same way the live banner does", () => {
    expect(formatStreamErrorText("deepseek-self stream HTTP 400: bad tool_calls")).toBe(
      "错误：deepseek-self stream HTTP 400: bad tool_calls",
    );
    expect(formatStreamErrorText("rate 429")).toBe("⚠️ rate 429");
    expect(formatStreamErrorText("x", true)).toBe("已停止生成。");
  });

  it("marks cancelled persisted errors", () => {
    expect(
      errorFlagsFromMessage({
        role: "assistant",
        content: "已停止生成。",
        metadata: { kind: "error", cancelled: true },
      }),
    ).toEqual({ error: true, cancelled: true });
  });
});
