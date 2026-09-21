import { describe, expect, it } from "vitest";

import {
  collectOfficeIds,
  officeAlignment,
  parseOfficeOutline,
  splitOfficeMath,
  unwrapOfficeLatex,
  type OfficeOutline,
} from "./officeOutline";
import { OFFICE_STYLE_PACKS, normalizeOfficeStyleId, themeFromStyle } from "./officeStyle";

const sample: OfficeOutline = {
  schema: "nlm.office.v1",
  doc_id: "off_abc",
  kind: "docx" as const,
  title: "季度方案",
  throughline: "增长必须先对齐交付节奏",
  plan: [
    { id: "p1", title: "背景" },
    { id: "p2", title: "目标" },
  ],
  requirements: [{ id: "r1", text: "写清背景", mapped_to: "p1" }],
  blocks: [
    { id: "cover_h1", type: "heading", level: 1, text: "季度方案", req: "cover" },
    { id: "b1", type: "heading", level: 2, text: "背景", req: "p1" },
    { id: "b2", type: "paragraph", text: "市场变化加快。", req: "p1" },
    { id: "b3", type: "equation", latex: "E = mc^2", display: "block", req: "p1" },
  ],
  last_ids: ["b1", "b2"],
};

describe("parseOfficeOutline", () => {
  it("parses JSON matching the Python outline fields", () => {
    const out = parseOfficeOutline(JSON.stringify(sample));
    expect(out?.doc_id).toBe("off_abc");
    expect(out?.kind).toBe("docx");
    expect(out?.blocks).toHaveLength(4);
    expect(out?.throughline).toBe("增长必须先对齐交付节奏");
    expect(out?.blocks?.[3]).toMatchObject({ type: "equation", latex: "E = mc^2" });
    expect(collectOfficeIds(out)).toEqual(["cover_h1", "b1", "b2", "b3"]);
  });

  it("splits inline math out of prose", () => {
    const parts = splitOfficeMath(String.raw`均值 $\mu_x$ 满足 $x^2+y^2=1$。`);
    expect(parts).toEqual([
      { kind: "text", value: "均值 " },
      { kind: "math", value: String.raw`\mu_x` },
      { kind: "text", value: " 满足 " },
      { kind: "math", value: "x^2+y^2=1" },
      { kind: "text", value: "。" },
    ]);
    expect(unwrapOfficeLatex(String.raw`$\mu_x$`)).toBe(String.raw`\mu_x`);
  });

  it("returns null for junk", () => {
    expect(parseOfficeOutline("not-json")).toBeNull();
    expect(parseOfficeOutline("")).toBeNull();
  });

  it("marks plan rows filled when a heading maps via req", () => {
    const out = parseOfficeOutline(sample)!;
    const align = officeAlignment(out);
    expect(align.filledPlan).toBe(1);
    expect(align.plan[0]?.filled).toBe(true);
    expect(align.plan[1]?.filled).toBe(false);
    expect(align.requirements[0]?.filled).toBe(true);
  });

  it("defaults style_id to commercial and expands academic tokens", () => {
    const commercial = parseOfficeOutline(sample)!;
    expect(commercial.style_id).toBe("commercial");
    expect(commercial.theme?.accent).toBe("#2A9D8F");
    const academic = parseOfficeOutline({ ...sample, style_id: "academic", theme: { accent: "#FF0000" } })!;
    expect(academic.style_id).toBe("academic");
    expect(academic.theme?.font_body).toBe("Times New Roman");
    expect(academic.theme?.paper).toBe("#FFFFFF");
    expect(academic.theme?.accent).toBe(OFFICE_STYLE_PACKS.academic.theme.accent);
    expect(normalizeOfficeStyleId("未知")).toBe("commercial");
    expect(themeFromStyle("academic").font_body).toBe("Times New Roman");
  });
});
