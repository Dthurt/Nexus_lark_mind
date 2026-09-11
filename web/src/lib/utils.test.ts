import { describe, expect, it } from "vitest";
import { normalizeTheme, themeLabel, THEME_ORDER } from "@/hooks/useTheme";
import { cn } from "@/lib/utils";

describe("useTheme", () => {
  it("normalizes aliases", () => {
    expect(normalizeTheme("light")).toBe("day");
    expect(normalizeTheme("dark")).toBe("night");
    expect(normalizeTheme("grey")).toBe("gray");
    expect(normalizeTheme("ocean")).toBe("ocean");
  });

  it("has five themes with Chinese labels", () => {
    expect(THEME_ORDER).toHaveLength(5);
    for (const t of THEME_ORDER) {
      expect(themeLabel(t).length).toBeGreaterThan(0);
    }
  });
});

describe("cn", () => {
  it("merges class names", () => {
    expect(cn("a", false && "b", "c")).toContain("a");
    expect(cn("px-2", "px-4")).toContain("px-4");
  });
});
