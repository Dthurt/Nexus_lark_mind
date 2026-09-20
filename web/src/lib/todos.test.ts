import { describe, expect, it } from "vitest";

import { latestTodoRows, todoProgress, todoRowsFromToolResult, todosAllSettled } from "./todos";

describe("todos helpers", () => {
  it("reads the latest timeline todos block", () => {
    const rows = latestTodoRows([
      { kind: "todos", items: [{ content: "old", status: "completed" }] },
      { kind: "msg" },
      { kind: "todos", items: [{ content: "new", status: "pending" }] },
    ]);
    expect(rows).toEqual([{ content: "new", status: "pending" }]);
  });

  it("hides the composer float only when every item is settled", () => {
    expect(todosAllSettled([{ status: "completed" }, { status: "cancelled" }])).toBe(true);
    expect(todosAllSettled([{ status: "completed" }, { status: "pending" }])).toBe(false);
    expect(todosAllSettled([])).toBe(true);
  });

  it("parses todo_write tool payloads", () => {
    expect(todoRowsFromToolResult({ items: [{ content: "A", status: "pending" }] })).toHaveLength(1);
    expect(todoRowsFromToolResult(JSON.stringify({ todos: [{ content: "B" }] }))).toEqual([{ content: "B" }]);
  });

  it("counts progress", () => {
    const p = todoProgress([
      { status: "completed" },
      { status: "in_progress", content: "写第三节" },
      { status: "pending" },
    ]);
    expect(p.done).toBe(1);
    expect(p.total).toBe(3);
    expect(p.current?.content).toBe("写第三节");
  });
});
