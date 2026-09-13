import { useCallback, useMemo, useState } from "react";
import { toast } from "sonner";

import { shortToolName } from "@/lib/toolChip";
import { lineDiff, writeFileAsDiff } from "@/lib/lineDiff";
import { postDiffRevert } from "@/api/endpoints";

export type DiffReviewItem = {
  id: string;
  callId: string;
  tool: string;
  path: string;
  kind: "write" | "edit";
  created?: boolean;
  previous?: string;
  previousOmitted?: boolean;
  old_string?: string;
  new_string?: string;
  content?: string;
  replace_all?: boolean;
  rows: ReturnType<typeof lineDiff>["rows"];
  stats: { adds: number; dels: number };
  status: "pending" | "accepted" | "rejected";
};

function buildFromTool(payload: any, args: Record<string, any>): DiffReviewItem | null {
  const tool = shortToolName(payload?.name) || "";
  if (tool !== "write_file" && tool !== "edit_file") return null;
  if (payload?.success === false) return null;

  const result = (payload?.result && typeof payload.result === "object" ? payload.result : {}) as any;
  const path = String(args.path || result.path || "").trim();
  if (!path) return null;

  const callId = String(payload?.id || payload?.call_id || "");
  const id = `diff_${callId || Date.now()}`;

  if (tool === "edit_file") {
    const oldS = String(args.old_string ?? "");
    const newS = String(args.new_string ?? "");
    const diff = lineDiff(oldS, newS);
    return {
      id,
      callId,
      tool,
      path,
      kind: "edit",
      old_string: oldS,
      new_string: newS,
      replace_all: !!args.replace_all,
      rows: diff.rows,
      stats: { adds: diff.stats.adds, dels: diff.stats.dels },
      status: "pending",
    };
  }

  const content = String(args.content ?? "");
  const previous = typeof result.previous === "string" ? result.previous : undefined;
  const created = result.created === true;
  const diff =
    previous != null ? lineDiff(previous, content) : writeFileAsDiff(content);
  return {
    id,
    callId,
    tool,
    path,
    kind: "write",
    created,
    previous,
    previousOmitted: !!result.previous_omitted,
    content,
    rows: diff.rows,
    stats: { adds: diff.stats.adds, dels: diff.stats.dels },
    status: "pending",
  };
}

export function useDiffReview() {
  const [items, setItems] = useState<DiffReviewItem[]>([]);

  const pending = useMemo(() => items.filter((i) => i.status === "pending"), [items]);

  const ingestToolResult = useCallback((payload: any, args?: Record<string, any>) => {
    const item = buildFromTool(payload, args || payload?.arguments || {});
    if (!item) return;
    setItems((prev) => {
      if (prev.some((p) => p.callId && p.callId === item.callId)) return prev;
      return [item, ...prev].slice(0, 40);
    });
  }, []);

  const accept = useCallback((id: string) => {
    setItems((prev) => prev.map((i) => (i.id === id ? { ...i, status: "accepted" } : i)));
  }, []);

  const dismiss = useCallback((id: string) => {
    setItems((prev) => prev.filter((i) => i.id !== id));
  }, []);

  const reject = useCallback(
    async (
      id: string,
      opts: { cwd: string; workspaceKind?: string; sessionId?: string },
    ) => {
      const item = items.find((i) => i.id === id);
      if (!item) return;
      if (!opts.cwd) {
        toast.error("需要本机工作区才能撤销");
        return;
      }
      try {
        await postDiffRevert(opts.sessionId || "_", {
          cwd: opts.cwd,
          workspace_kind: opts.workspaceKind || "local",
          path: item.path,
          tool: item.tool,
          created: item.created,
          previous: item.previous,
          old_string: item.old_string,
          new_string: item.new_string,
          replace_all: item.replace_all,
        });
        setItems((prev) => prev.map((i) => (i.id === id ? { ...i, status: "rejected" } : i)));
        toast.success(`已撤销 ${item.path}`);
        window.setTimeout(() => dismiss(id), 600);
      } catch (err: any) {
        toast.error(String(err?.message || err));
      }
    },
    [items, dismiss],
  );

  return { items, pending, ingestToolResult, accept, reject, dismiss };
}

export type DiffReviewApi = ReturnType<typeof useDiffReview>;
