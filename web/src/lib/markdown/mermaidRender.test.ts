import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("mermaid", () => ({
  default: {
    initialize: vi.fn(),
    render: vi.fn(async (id: string) => ({
      svg: `<svg id="${id}" xmlns="http://www.w3.org/2000/svg" width="100%" height="100%" viewBox="0 0 240 90"><rect width="240" height="90" fill="#38bdf8"/></svg>`,
    })),
  },
}));

import { renderMermaidIn } from "@/lib/markdown/render";

describe("renderMermaidIn", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("keeps the inline SVG after mermaid temp-node cleanup", async () => {
    const root = document.createElement("div");
    root.className = "nlm-md";
    root.innerHTML =
      '<div class="mermaid-block" data-mermaid-host="1"><pre class="mermaid">flowchart LR\nA-->B</pre></div>';
    document.body.appendChild(root);

    await renderMermaidIn(root, {});

    const svg = root.querySelector(".mermaid-stage svg") as SVGSVGElement | null;
    expect(svg).toBeTruthy();
    expect(svg?.getAttribute("width")).toBe("240");
    expect(svg?.getAttribute("height")).toBe("90");
    expect(root.querySelector(".mermaid-block")?.getAttribute("data-processed")).toBe("ok");
  });
});
