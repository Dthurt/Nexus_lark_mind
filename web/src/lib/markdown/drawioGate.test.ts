import { describe, expect, it } from "vitest";

import { drawioBlockedMarkdownHtml, mxfileToOfflineSvg } from "@/lib/markdown/drawio";
import { renderMarkdown } from "@/lib/markdown/render";

describe("fast tier drawio gate", () => {
  it("blocks drawio fences when allowDrawio=false", () => {
    const html = renderMarkdown("```drawio\n<mxfile></mxfile>\n```", {
      allowDrawio: false,
    });
    expect(html).toContain("drawio-blocked");
    expect(html).toContain("Fast 体验档");
  });

  it("allows drawio by default", () => {
    const html = renderMarkdown("```drawio\n<mxfile></mxfile>\n```");
    expect(html).toContain("drawio-block");
    expect(html).not.toContain("drawio-blocked");
  });

  it("drawioBlockedMarkdownHtml marks blocked", () => {
    expect(drawioBlockedMarkdownHtml("<mxfile/>")).toContain('data-drawio-blocked="1"');
  });
});

describe("offline drawio svg", () => {
  it("renders vertex cells", () => {
    const xml = `<mxfile><diagram><mxGraphModel><root>
      <mxCell id="0"/><mxCell id="1" parent="0"/>
      <mxCell id="2" value="Hello" vertex="1" parent="1">
        <mxGeometry x="10" y="20" width="100" height="40" as="geometry"/>
      </mxCell>
    </root></mxGraphModel></diagram></mxfile>`;
    const svg = mxfileToOfflineSvg(xml);
    expect(svg).toContain("<svg");
    expect(svg).toContain("Hello");
  });
});
