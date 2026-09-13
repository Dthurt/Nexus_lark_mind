import { describe, expect, it } from "vitest";

import { createCanvasDoc, loadCanvasSession, saveCanvasSession } from "./canvasDoc";
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
  });

  it("createCanvasDoc titles for echarts/drawio", () => {
    expect(createCanvasDoc({ kind: "echarts", body: "{}" }).title).toBe("ECharts");
    expect(createCanvasDoc({ kind: "drawio", body: "<mxfile/>" }).title).toBe("Draw.io");
  });
});

describe("parseEchartsOption", () => {
  it("parses fenced and trailing-comma JSON", () => {
    const opt = parseEchartsOption('```echarts\n{"series":[{"type":"bar","data":[1,]}],}\n```');
    expect(opt.series[0].type).toBe("bar");
    expect(opt.series[0].data).toEqual([1]);
  });
});
