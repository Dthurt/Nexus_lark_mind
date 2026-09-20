import { describe, expect, it } from "vitest";

import { applyOfficePreview, emptyOfficePreview } from "./officePreview";
import type { OfficeOutline } from "./officeOutline";

const cover: OfficeOutline = {
  doc_id: "off_1",
  kind: "pptx",
  title: "Kickoff",
  plan: [{ id: "p1", title: "目标" }],
  slides: [{ id: "cover_title", type: "title", title: "Kickoff", subtitle: "Q3" }],
  last_op: "create",
  last_ids: ["cover_title"],
};

describe("applyOfficePreview", () => {
  it("opens from a full outline (office_create stream)", () => {
    const next = applyOfficePreview(emptyOfficePreview(), { op: "create", outline: cover });
    expect(next.outline?.doc_id).toBe("off_1");
    expect(next.enteringIds).toEqual(["cover_title"]);
    expect(next.writing).toBe(false);
  });

  it("marks only new slide ids as entering on append", () => {
    const created = applyOfficePreview(emptyOfficePreview(), { outline: cover });
    const appended: OfficeOutline = {
      ...cover,
      slides: [
        ...(cover.slides || []),
        { id: "s2", type: "bullets", title: "目标", items: ["增长", "质量"], req: "p1" },
      ],
      last_op: "append",
      last_ids: ["s2"],
    };
    const next = applyOfficePreview(created, { op: "append", outline: appended });
    expect(next.enteringIds).toEqual(["s2"]);
    expect(next.outline?.slides).toHaveLength(2);
  });

  it("applies a single block without a full outline", () => {
    const word: OfficeOutline = {
      doc_id: "off_w",
      kind: "docx",
      title: "Memo",
      blocks: [{ id: "h1", type: "heading", level: 1, text: "Memo" }],
    };
    const base = applyOfficePreview(emptyOfficePreview(), { outline: word });
    const next = applyOfficePreview(base, {
      op: "append",
      block: { id: "p1", type: "paragraph", text: "Hello" },
    });
    expect(next.outline?.blocks).toHaveLength(2);
    expect(next.enteringIds).toContain("p1");
  });

  it("sets writing without clobbering the outline", () => {
    const base = applyOfficePreview(emptyOfficePreview(), { outline: cover });
    const next = applyOfficePreview(base, { writing: true });
    expect(next.writing).toBe(true);
    expect(next.outline?.doc_id).toBe("off_1");
  });
});
