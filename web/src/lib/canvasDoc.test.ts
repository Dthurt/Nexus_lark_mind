import { describe, expect, it } from "vitest";

import {
  applyCanvasOpen,
  archiveCanvasDoc,
  createCanvasDoc,
  loadCanvasSession,
  OFFICE_SESSION_SOURCE,
  saveCanvasSession,
} from "./canvasDoc";
import { parseEchartsOption } from "./markdown/echarts";

describe("canvasDoc", () => {
  it("createCanvasDoc fills title from kind", () => {
    const doc = createCanvasDoc({ kind: "mermaid", body: "graph TD; A-->B" });
    expect(doc.kind).toBe("mermaid");
    expect(doc.title).toBe("Mermaid");
    expect(doc.body).toContain("A-->B");
    expect(doc.id).toMatch(/^cv_/);
  });

  it("round-trips session state in localStorage", () => {
    const sid = "sess_canvas_test";
    const doc = createCanvasDoc({
      kind: "delivery",
      title: "Ship",
      body: "# ok",
      dedupeKey: "delivery:1",
    });
    saveCanvasSession(sid, { open: true, activeId: doc.id, docs: [doc] });
    const snap = loadCanvasSession(sid);
    expect(snap.open).toBe(true);
    expect(snap.activeId).toBe(doc.id);
    expect(snap.docs).toHaveLength(1);
    expect(snap.docs[0]?.title).toBe("Ship");
    expect(snap.recent?.[0]?.title).toBe("Ship");
  });

  it("keeps archived docs after the pane snapshot is closed", () => {
    const sid = "sess_canvas_recent";
    const doc = createCanvasDoc({ kind: "office", title: "论文", body: '{"doc_id":"off_x"}' });
    saveCanvasSession(sid, { open: false, activeId: doc.id, docs: [doc], recent: [doc] });
    const snap = loadCanvasSession(sid);
    expect(snap.open).toBe(false);
    expect(snap.docs).toHaveLength(1);
    expect(snap.recent?.[0]?.title).toBe("论文");
    const archived = archiveCanvasDoc([], doc);
    expect(archived[0]?.id).toBe(doc.id);
  });

  it("createCanvasDoc titles for echarts/drawio/office", () => {
    expect(createCanvasDoc({ kind: "echarts", body: "{}" }).title).toBe("ECharts");
    expect(createCanvasDoc({ kind: "drawio", body: "<mxfile/>" }).title).toBe("Draw.io");
    const office = createCanvasDoc({ kind: "office", body: '{"kind":"docx"}' });
    expect(office.title).toBe("Office");
    expect(office.source).toBe(OFFICE_SESSION_SOURCE);
  });

  it("reuses office canvas when source was a file path but append uses doc_id", () => {
    const first = applyCanvasOpen([], {
      kind: "office",
      title: "季度方案",
      body: JSON.stringify({ schema: "nlm.office.v1", doc_id: "off_a", kind: "docx", title: "季度方案", blocks: [] }),
      dedupeKey: "off_a",
      source: ".nlm/office/季度方案.docx",
    });
    expect(first.reused).toBe(false);
    expect(first.docs).toHaveLength(1);

    const appended = applyCanvasOpen(first.docs, {
      kind: "office",
      title: "季度方案",
      body: JSON.stringify({
        schema: "nlm.office.v1",
        doc_id: "off_a",
        kind: "docx",
        title: "季度方案",
        blocks: [{ id: "b1", type: "paragraph", text: "追加" }],
      }),
      dedupeKey: "off_a",
      source: ".nlm/office/季度方案.docx",
    });
    expect(appended.reused).toBe(true);
    expect(appended.docs).toHaveLength(1);
    expect(appended.activeId).toBe(first.activeId);
    expect(appended.docs[0]?.body).toContain("追加");
  });

  it("keeps one office canvas when a later create has a new doc_id", () => {
    const first = applyCanvasOpen([], {
      kind: "office",
      title: "Word",
      body: JSON.stringify({ doc_id: "off_1", kind: "docx", title: "Word" }),
      dedupeKey: "off_1",
    });
    const second = applyCanvasOpen(first.docs, {
      kind: "office",
      title: "PPT",
      body: JSON.stringify({ doc_id: "off_2", kind: "pptx", title: "PPT" }),
      dedupeKey: "off_2",
    });
    expect(second.reused).toBe(true);
    expect(second.docs).toHaveLength(1);
    expect(second.docs[0]?.title).toBe("PPT");
    expect(second.docs[0]?.kind).toBe("office");
  });

  it("switches the open mermaid pane to office instead of stacking", () => {
    const mermaid = createCanvasDoc({ kind: "mermaid", title: "Flow", body: "graph TD; A-->B", dedupeKey: "mermaid:1" });
    const next = applyCanvasOpen([mermaid], {
      kind: "office",
      title: "方案",
      body: JSON.stringify({ doc_id: "off_x", kind: "docx", title: "方案" }),
      dedupeKey: "off_x",
    }, { activeId: mermaid.id, paneOpen: true });
    expect(next.reused).toBe(true);
    expect(next.docs).toHaveLength(1);
    expect(next.docs[0]?.id).toBe(mermaid.id);
    expect(next.docs[0]?.kind).toBe("office");
    expect(next.docs[0]?.title).toBe("方案");
  });

  it("does not steal a closed mermaid tab when first opening office", () => {
    const mermaid = createCanvasDoc({ kind: "mermaid", title: "Flow", body: "graph TD; A-->B", dedupeKey: "mermaid:1" });
    const next = applyCanvasOpen([mermaid], {
      kind: "office",
      title: "方案",
      body: JSON.stringify({ doc_id: "off_x", kind: "docx", title: "方案" }),
      dedupeKey: "off_x",
    }, { activeId: mermaid.id, paneOpen: false });
    expect(next.reused).toBe(false);
    expect(next.docs).toHaveLength(2);
    expect(next.docs[0]?.kind).toBe("office");
    expect(next.docs[1]?.kind).toBe("mermaid");
  });

  it("keeps mermaid dedupe by source+kind", () => {
    const first = applyCanvasOpen([], {
      kind: "mermaid",
      title: "Flow",
      body: "graph TD; A-->B",
      dedupeKey: "mermaid:1",
    });
    const again = applyCanvasOpen(first.docs, {
      kind: "mermaid",
      title: "Flow",
      body: "graph TD; A-->C",
      dedupeKey: "mermaid:1",
    });
    expect(again.reused).toBe(true);
    expect(again.docs).toHaveLength(1);
    expect(again.docs[0]?.body).toContain("A-->C");
  });
});

describe("parseEchartsOption", () => {
  it("parses fenced and trailing-comma JSON", () => {
    const opt = parseEchartsOption('```echarts\n{"series":[{"type":"bar","data":[1,]}],}\n```');
    expect(opt.series[0].type).toBe("bar");
    expect(opt.series[0].data).toEqual([1]);
  });
});
