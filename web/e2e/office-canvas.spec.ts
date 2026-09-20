import { expect, test } from "@playwright/test";

import { openWorkbench, requireAdapters } from "./helpers";

const wordOutline = {
  schema: "nlm.office.v1",
  doc_id: "off_e76ccf1cddf0",
  kind: "docx",
  title: "季度增长方案",
  subtitle: "2026 Q3",
  throughline: "增长必须先对齐交付节奏",
  plan: [
    { id: "p1", title: "背景" },
    { id: "p2", title: "目标与指标" },
    { id: "p3", title: "预算" },
  ],
  blocks: [
    { id: "cover_h1", type: "heading", level: 1, text: "季度增长方案" },
    { id: "b1", type: "heading", level: 2, text: "背景", req: "p1" },
    { id: "b2", type: "paragraph", text: "本季市场节奏加快。", req: "p1" },
    { id: "b3", type: "quote", text: "先对齐结构，再写正文。", attribution: "工作台", req: "p1" },
    {
      id: "b4",
      type: "table",
      headers: ["项", "值"],
      rows: [["预算", "120"]],
      req: "p3",
    },
    { id: "b5eq", type: "equation", latex: "E = mc^2", display: "block", req: "p2" },
  ],
  last_ids: ["b4"],
  download_url: "/api/office/files/off_e76ccf1cddf0",
  file_name: "季度增长方案.docx",
};

const pptOutline = {
  schema: "nlm.office.v1",
  doc_id: "off_09a14c94dbb6",
  kind: "pptx",
  title: "Q3 Kickoff",
  throughline: "先对齐目标再对比路径",
  plan: [
    { id: "p1", title: "目标" },
    { id: "p2", title: "对比" },
  ],
  slides: [
    { id: "cover_title", type: "title", title: "Q3 Kickoff", subtitle: "对齐用户要求" },
    { id: "s2", type: "section", title: "目标", kicker: "Part 1", req: "p1" },
    {
      id: "s3",
      type: "two_column",
      title: "对比",
      left: { heading: "现状", items: ["周期长"] },
      right: { heading: "目标", items: ["更快交付"] },
      req: "p2",
    },
  ],
  last_ids: ["s3"],
  download_url: "/api/office/files/off_09a14c94dbb6",
};

test.describe("office canvas", () => {
  test("word then ppt preview, mermaid canvas, knowledge page", async ({ page, request }) => {
    await requireAdapters(request);
    await openWorkbench(page);

    await expect(page.getByTestId("view-ring-knowledge")).toBeVisible();
    await expect(page.getByTestId("empty-open-knowledge")).toBeVisible();

    await page.evaluate((outline) => {
      window.dispatchEvent(
        new CustomEvent("nlm-canvas-open", {
          detail: {
            kind: "office",
            title: outline.title,
            body: JSON.stringify(outline),
            dedupeKey: outline.doc_id,
          },
        }),
      );
    }, wordOutline);

    const office = page.getByTestId("office-canvas");
    await expect(office).toBeVisible();
    await expect(page.getByTestId("canvas-pane")).toHaveCount(1);
    await expect(page.getByTestId("canvas-tab")).toHaveCount(1);
    await expect(office.getByText("季度增长方案").first()).toBeVisible();
    await expect(office.getByText("先对齐结构，再写正文。")).toBeVisible();
    await expect(office.getByText("预算")).toBeVisible();
    await expect(page.getByTestId("office-structure")).toBeVisible();
    await expect(page.getByTestId("office-throughline")).toContainText("增长必须先对齐交付节奏");
    await expect(page.getByTestId("office-equation")).toBeVisible();
    await expect(page.getByTestId("office-download")).toBeVisible();

    const appendedWord = {
      ...wordOutline,
      blocks: [
        ...wordOutline.blocks,
        { id: "b5", type: "paragraph", text: "追加的一节正文。", req: "p2" },
      ],
      last_op: "append",
      last_ids: ["b5"],
    };
    await page.evaluate((outline) => {
      window.dispatchEvent(new CustomEvent("nlm-office-writing", { detail: { name: "office_append" } }));
      window.dispatchEvent(
        new CustomEvent("nlm-canvas-open", {
          detail: {
            kind: "office",
            title: outline.title,
            body: JSON.stringify(outline),
            dedupeKey: outline.doc_id,
            source: "/tmp/office-mismatch.docx",
          },
        }),
      );
    }, appendedWord);
    await expect(office.getByText("追加的一节正文。")).toBeVisible();
    await expect(page.getByTestId("canvas-pane")).toHaveCount(1);
    await expect(page.getByTestId("canvas-tab")).toHaveCount(1);
    await expect(page.getByTestId("office-canvas")).toHaveCount(1);

    await page.evaluate((outline) => {
      window.dispatchEvent(new CustomEvent("nlm-office-writing", { detail: { name: "office_append" } }));
      window.dispatchEvent(
        new CustomEvent("nlm-canvas-open", {
          detail: {
            kind: "office",
            title: outline.title,
            body: JSON.stringify(outline),
            dedupeKey: outline.doc_id,
          },
        }),
      );
    }, pptOutline);

    await expect(office.getByText("Q3 Kickoff").first()).toBeVisible();
    await expect(office.getByText("更快交付")).toBeVisible();
    await expect(page.getByTestId("canvas-pane")).toHaveCount(1);
    await expect(page.getByTestId("canvas-tab")).toHaveCount(1);
    await expect(page.getByTestId("office-canvas")).toHaveCount(1);

    await page.evaluate(() => {
      window.dispatchEvent(
        new CustomEvent("nlm-canvas-open", {
          detail: {
            kind: "mermaid",
            title: "Flow",
            body: "graph TD; A-->B",
            dedupeKey: "mermaid:e2e",
          },
        }),
      );
    });
    await expect(page.getByText("Mermaid", { exact: false }).first()).toBeVisible();
    await expect(page.getByTestId("canvas-pane")).toHaveCount(1);
    await expect(page.getByTestId("canvas-tab")).toHaveCount(2);

    await page.getByTestId("view-ring-knowledge").click();
    await expect(page.getByTestId("knowledge-page")).toBeVisible();
    await expect(page.getByTestId("knowledge-search-input")).toBeVisible();
  });

  test("open mermaid then office switches the same canvas tab", async ({ page, request }) => {
    await requireAdapters(request);
    await openWorkbench(page);

    await page.evaluate(() => {
      window.dispatchEvent(
        new CustomEvent("nlm-canvas-open", {
          detail: {
            kind: "mermaid",
            title: "Flow",
            body: "graph TD; A-->B",
            dedupeKey: "mermaid:switch",
          },
        }),
      );
    });
    await expect(page.getByTestId("canvas-pane")).toBeVisible();
    await expect(page.getByTestId("canvas-tab")).toHaveCount(1);

    await page.evaluate((outline) => {
      window.dispatchEvent(
        new CustomEvent("nlm-canvas-open", {
          detail: {
            kind: "office",
            title: outline.title,
            body: JSON.stringify(outline),
            dedupeKey: outline.doc_id,
          },
        }),
      );
    }, wordOutline);

    await expect(page.getByTestId("office-canvas")).toBeVisible();
    await expect(page.getByTestId("canvas-pane")).toHaveCount(1);
    await expect(page.getByTestId("canvas-tab")).toHaveCount(1);
    await expect(page.getByTestId("office-canvas").getByText("季度增长方案").first()).toBeVisible();
  });

  test("closing canvas pane restores the last office document", async ({ page, request }) => {
    await requireAdapters(request);
    await openWorkbench(page);

    await page.evaluate((outline) => {
      window.dispatchEvent(
        new CustomEvent("nlm-canvas-open", {
          detail: {
            kind: "office",
            title: outline.title,
            body: JSON.stringify(outline),
            dedupeKey: outline.doc_id,
          },
        }),
      );
    }, wordOutline);

    await expect(page.getByTestId("office-canvas")).toBeVisible();
    await page.getByTestId("canvas-close").click();
    await expect(page.getByTestId("canvas-pane")).toHaveCount(0);
    await expect(page.getByTestId("canvas-reopen-last")).toBeVisible();

    await page.getByTestId("canvas-toggle").click();
    await expect(page.getByTestId("canvas-pane")).toBeVisible();
    await expect(page.getByTestId("office-canvas")).toBeVisible();
    await expect(page.getByTestId("office-canvas").getByText("季度增长方案").first()).toBeVisible();
    await expect(page.getByTestId("office-download")).toBeVisible();
  });
});
