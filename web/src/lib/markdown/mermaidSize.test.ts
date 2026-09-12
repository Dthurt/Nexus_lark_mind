import { describe, expect, it } from "vitest";

import { normalizeMermaidSvgSize } from "@/lib/markdown/render";

function makeSvg(attrs: Record<string, string>): SVGSVGElement {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  for (const [k, v] of Object.entries(attrs)) svg.setAttribute(k, v);
  return svg;
}

describe("normalizeMermaidSvgSize", () => {
  it("replaces percent width with viewBox pixels", () => {
    const svg = makeSvg({
      width: "100%",
      height: "100%",
      viewBox: "0 0 420 180",
    });
    normalizeMermaidSvgSize(svg);
    expect(svg.getAttribute("width")).toBe("420");
    expect(svg.getAttribute("height")).toBe("180");
    expect(svg.style.maxWidth).toBe("100%");
    expect(svg.style.display).toBe("block");
  });

  it("keeps explicit pixel sizes", () => {
    const svg = makeSvg({ width: "300", height: "120", viewBox: "0 0 300 120" });
    normalizeMermaidSvgSize(svg);
    expect(svg.getAttribute("width")).toBe("300");
    expect(svg.getAttribute("height")).toBe("120");
  });

  it("fills missing size from viewBox", () => {
    const svg = makeSvg({ viewBox: "0 0 200 90" });
    normalizeMermaidSvgSize(svg);
    expect(svg.getAttribute("width")).toBe("200");
    expect(svg.getAttribute("height")).toBe("90");
  });
});
