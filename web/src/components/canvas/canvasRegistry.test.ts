import { describe, expect, it } from "vitest";

import { parseTableBody } from "@/components/canvas/TableCanvasView";
import { registerCanvasView, getCanvasView, unregisterCanvasView } from "@/components/canvas/canvasRegistry";

describe("parseTableBody", () => {
  it("parses JSON object array", () => {
    const { headers, rows } = parseTableBody('[{"a":1,"b":2},{"a":3,"b":4}]');
    expect(headers).toEqual(["a", "b"]);
    expect(rows).toEqual([
      ["1", "2"],
      ["3", "4"],
    ]);
  });

  it("parses markdown pipe table", () => {
    const { headers, rows } = parseTableBody("| x | y |\n| --- | --- |\n| 1 | 2 |");
    expect(headers).toEqual(["x", "y"]);
    expect(rows[0]).toEqual(["1", "2"]);
  });
});

describe("canvasRegistry", () => {
  it("registers and resolves views", () => {
    const Comp = () => null;
    registerCanvasView("custom-p3", Comp as any);
    expect(getCanvasView("custom-p3")).toBe(Comp);
    unregisterCanvasView("custom-p3");
    expect(getCanvasView("custom-p3")).toBeNull();
  });
});
