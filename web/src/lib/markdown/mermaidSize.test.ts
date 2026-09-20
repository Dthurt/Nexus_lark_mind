import { describe, expect, it } from "vitest";

import { cleanupMermaidArtifacts, normalizeMermaidSvgSize } from "@/lib/markdown/render";

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
    expect(svg.style.aspectRatio).toBe("420 / 180");
  });

  it("does not treat 100% as 100px when viewBox is missing", () => {
    const svg = makeSvg({ width: "100%", height: "100%" });
    normalizeMermaidSvgSize(svg);
    expect(svg.getAttribute("width")).toBe("100%");
    expect(svg.getAttribute("height")).toBe("100%");
  });

  it("keeps explicit pixel sizes", () => {
    const svg = makeSvg({ width: "300", height: "120", viewBox: "0 0 300 120" });
    normalizeMermaidSvgSize(svg);
    expect(svg.getAttribute("width")).toBe("300");
    expect(svg.getAttribute("height")).toBe("120");
    expect(svg.style.aspectRatio).toBe("300 / 120");
  });

  it("fills missing size from viewBox", () => {
    const svg = makeSvg({ viewBox: "0 0 200 90" });
    normalizeMermaidSvgSize(svg);
    expect(svg.getAttribute("width")).toBe("200");
    expect(svg.getAttribute("height")).toBe("90");
  });
});

describe("cleanupMermaidArtifacts", () => {
  it("does not remove the SVG that was just mounted in mermaid-stage", () => {
    const id = "nlm-mmd-test-live";
    const block = document.createElement("div");
    block.className = "mermaid-block";
    const stage = document.createElement("div");
    stage.className = "mermaid-stage";
    const svg = makeSvg({ id, viewBox: "0 0 120 80" });
    stage.appendChild(svg);
    block.appendChild(stage);
    document.body.appendChild(block);

    const stray = document.createElement("div");
    stray.id = `d${id}`;
    document.body.appendChild(stray);

    cleanupMermaidArtifacts(id);

    expect(document.getElementById(id)).toBe(svg);
    expect(stage.contains(svg)).toBe(true);
    expect(document.getElementById(`d${id}`)).toBeNull();

    block.remove();
  });
});
