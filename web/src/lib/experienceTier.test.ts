import { describe, expect, it } from "vitest";

import {
  modelStrength,
  suggestStrongerModel,
  tierMeetsModelFloor,
} from "@/lib/experienceTier";

describe("experienceTier model floor", () => {
  it("scores weak / mid / strong", () => {
    expect(modelStrength("gpt-4o-mini")).toBe(0);
    expect(modelStrength("glm-4.7")).toBe(1);
    expect(modelStrength("claude-sonnet-4")).toBe(2);
  });

  it("enforces soft floors by tier", () => {
    expect(tierMeetsModelFloor("fast", "gpt-4o-mini")).toBe(true);
    expect(tierMeetsModelFloor("high", "gpt-4o-mini")).toBe(false);
    expect(tierMeetsModelFloor("high", "claude-opus-4")).toBe(true);
  });

  it("suggests a stronger catalog model", () => {
    expect(
      suggestStrongerModel(
        [{ value: "gpt-4o-mini" }, { value: "claude-sonnet-4" }],
        "gpt-4o-mini",
      ),
    ).toBe("claude-sonnet-4");
    expect(suggestStrongerModel([{ value: "gpt-4o-mini" }], "gpt-4o-mini")).toBe(null);
  });
});
