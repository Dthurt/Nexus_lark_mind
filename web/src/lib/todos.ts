/** Shared todo helpers for timeline cards + composer float. */

export type TodoRow = {
  id?: string;
  content?: string;
  status?: string;
};

export function latestTodoRows(items: Array<{ kind?: string; items?: TodoRow[] }> | null | undefined): TodoRow[] {
  const list = items || [];
  for (let i = list.length - 1; i >= 0; i -= 1) {
    if (list[i]?.kind === "todos") {
      return Array.isArray(list[i].items) ? list[i].items! : [];
    }
  }
  return [];
}

export function todosAllSettled(rows: TodoRow[]): boolean {
  if (!rows.length) return true;
  return rows.every((r) => r.status === "completed" || r.status === "cancelled");
}

export function todoProgress(rows: TodoRow[]): { done: number; total: number; current?: TodoRow } {
  const total = rows.length;
  const done = rows.filter((r) => r.status === "completed" || r.status === "cancelled").length;
  const current = rows.find((r) => r.status === "in_progress") || rows.find((r) => r.status === "pending");
  return { done, total, current };
}

export function todoRowsFromToolResult(raw: unknown): TodoRow[] {
  let value: unknown = raw;
  if (typeof raw === "string") {
    const text = raw.trim();
    if (!text) return [];
    try {
      value = JSON.parse(text);
    } catch {
      return [];
    }
  }
  if (value && typeof value === "object") {
    const obj = value as { items?: unknown; todos?: unknown; result?: { items?: unknown } };
    const nested = obj.items || obj.todos || obj.result?.items;
    if (Array.isArray(nested)) return nested as TodoRow[];
  }
  return Array.isArray(value) ? (value as TodoRow[]) : [];
}
