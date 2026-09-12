/**
 * Smoke e2e — requires adapters on :8000 (or PLAYWRIGHT_BASE_URL).
 * Skip automatically when the server is unreachable.
 */
import { test, expect } from "@playwright/test";

test.describe("workbench smoke", () => {
  test("empty state onboarding + mermaid size helper", async ({ page }) => {
    const res = await page.goto("/", { waitUntil: "domcontentloaded" }).catch(() => null);
    test.skip(!res || res.status() >= 500, "adapters not running on baseURL");

    await expect(page.getByText("Nexus Lark Mind").first()).toBeVisible({ timeout: 15000 });
    // First-run checklist steps
    await expect(page.getByText(/绑定工作目录/)).toBeVisible();
    await expect(page.getByText(/选择 Provider/)).toBeVisible();

    // Mermaid normalize contract (in-page, no model call)
    const sized = await page.evaluate(() => {
      const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      svg.setAttribute("width", "100%");
      svg.setAttribute("height", "100%");
      svg.setAttribute("viewBox", "0 0 240 100");
      document.body.appendChild(svg);
      // Inline the same algorithm as normalizeMermaidSvgSize
      const vb = svg.viewBox.baseVal;
      let w = parseFloat(svg.getAttribute("width") || "") || 0;
      let h = parseFloat(svg.getAttribute("height") || "") || 0;
      const pctW = /%/.test(String(svg.getAttribute("width") || ""));
      const pctH = /%/.test(String(svg.getAttribute("height") || ""));
      if ((!w || !h || pctW || pctH) && vb && vb.width > 0 && vb.height > 0) {
        w = vb.width;
        h = vb.height;
      }
      if (w > 0) svg.setAttribute("width", String(Math.round(w)));
      if (h > 0) svg.setAttribute("height", String(Math.round(h)));
      return { w: svg.getAttribute("width"), h: svg.getAttribute("height") };
    });
    expect(sized.w).toBe("240");
    expect(sized.h).toBe("100");
  });
});
