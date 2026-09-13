import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import type { CanvasViewProps } from "@/components/canvas/canvasRegistry";
import { CanvasEditorShell, useSyncedDraft } from "@/components/canvas/CanvasEditorShell";
import { cn } from "@/lib/utils";

/** Parse JSON array-of-objects or pipe markdown table into rows. */
export function parseTableBody(raw: string): { headers: string[]; rows: string[][] } {
  const text = String(raw || "").trim();
  if (!text) return { headers: [], rows: [] };

  if (text.startsWith("[") || text.startsWith("{")) {
    try {
      const data = JSON.parse(text);
      const list = Array.isArray(data) ? data : Array.isArray(data?.rows) ? data.rows : null;
      if (Array.isArray(list) && list.length) {
        if (typeof list[0] === "object" && !Array.isArray(list[0])) {
          const headers = Object.keys(list[0] as object);
          const rows = list.map((row: any) => headers.map((h) => String(row?.[h] ?? "")));
          return { headers, rows };
        }
        if (Array.isArray(list[0])) {
          const headers = (list[0] as any[]).map(String);
          const rows = list.slice(1).map((r: any) => (Array.isArray(r) ? r.map(String) : [String(r)]));
          return { headers, rows };
        }
      }
    } catch {
      /* fall through */
    }
  }

  const lines = text
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean)
    .filter((l) => !/^\|?\s*:?-{3,}/.test(l));
  const split = (line: string) =>
    line
      .replace(/^\|/, "")
      .replace(/\|$/, "")
      .split("|")
      .map((c) => c.trim());
  if (!lines.length) return { headers: [], rows: [] };
  const headers = split(lines[0]);
  const rows = lines.slice(1).map(split);
  return { headers, rows };
}

export function TableCanvasView({ doc, onCommit }: CanvasViewProps) {
  const [draft, setDraft] = useSyncedDraft(doc.body);
  const [mode, setMode] = useState<"preview" | "source" | "split">("split");
  const [status, setStatus] = useState("");
  const [statusError, setStatusError] = useState(false);
  const parsed = useMemo(() => parseTableBody(draft), [draft]);

  const apply = () => {
    onCommit(draft);
    setStatus("已写回 Canvas");
    setStatusError(false);
    window.setTimeout(() => setStatus(""), 1200);
  };

  return (
    <CanvasEditorShell
      kindLabel="Table"
      draft={draft}
      onDraftChange={setDraft}
      onApply={apply}
      status={status}
      statusError={statusError}
      editorMode={mode}
      onEditorModeChange={setMode}
      extraActions={
        <Button
          type="button"
          size="sm"
          variant="ghost"
          className="h-6 px-2 text-[11px]"
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(draft);
              setStatus("已复制");
            } catch (err: any) {
              setStatus(String(err?.message || err));
              setStatusError(true);
            }
          }}
        >
          复制
        </Button>
      }
    >
      <div className="overflow-auto p-2">
        {!parsed.headers.length ? (
          <p className="m-0 text-[11px] text-muted-foreground">
            空表。源码可用 JSON 对象数组，或 Markdown 管道表。
          </p>
        ) : (
          <table className="w-full border-collapse text-left text-[11px]">
            <thead>
              <tr>
                {parsed.headers.map((h) => (
                  <th
                    key={h}
                    className="border border-border/60 bg-muted/40 px-2 py-1 font-medium text-foreground"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {parsed.rows.map((row, i) => (
                <tr key={i} className={cn(i % 2 ? "bg-muted/20" : undefined)}>
                  {parsed.headers.map((_, j) => (
                    <td key={j} className="border border-border/50 px-2 py-1 text-foreground/90">
                      {row[j] ?? ""}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </CanvasEditorShell>
  );
}
