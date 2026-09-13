/** Pure helpers for Codex-style tool chips. */

import type { ToolRunStatus } from "@/lib/toolStatus";

export function shortToolName(name?: string): string {
  const raw = String(name || "tool");
  return (
    raw
      .replace(/^builtin_workspace_/, "")
      .replace(/^cli_/, "")
      .split(".")
      .pop() || raw
  );
}

export function formatToolDurationMs(durationMs?: number | null): string {
  if (durationMs == null) return "";
  const n = Number(durationMs);
  if (!Number.isFinite(n)) return `${durationMs} ms`;
  if (n >= 1000) return `${(n / 1000).toFixed(n >= 10_000 ? 0 : 1)}s`;
  return `${n.toFixed(n >= 100 ? 0 : 1)} ms`;
}

/** Default expand: running / failed / highlighted / explicit open. */
export function shouldAutoExpandTool(opts: {
  status: ToolRunStatus;
  highlighted?: boolean;
  forcedOpen?: boolean;
}): boolean {
  if (opts.forcedOpen) return true;
  if (opts.highlighted) return true;
  if (opts.status === "running" || opts.status === "failed") return true;
  return false;
}

export function oneLinePreview(value: unknown, limit = 96): string {
  if (value == null) return "";
  let text: string;
  if (typeof value === "string") {
    text = value;
  } else {
    try {
      text = JSON.stringify(value);
    } catch {
      text = String(value);
    }
  }
  text = text.replace(/\s+/g, " ").trim();
  if (text.length <= limit) return text;
  return `${text.slice(0, limit - 1)}…`;
}
