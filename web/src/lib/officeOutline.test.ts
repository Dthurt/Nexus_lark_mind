import { describe, expect, it } from "vitest";

import {
  collectOfficeIds,
  officeAlignment,
  parseOfficeOutline,
  type OfficeOutline,
} from "./officeOutline";

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
});
