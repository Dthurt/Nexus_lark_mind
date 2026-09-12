/** Plan → Diagram → Code changes → Delivery artifact helpers. */

export type DiagramFence = {
  lang: string;
  body: string;
};

export type DeliverySeed = {
  title?: string;
  plan: string;
  callId?: string;
  sessionId?: string;
  acceptedAt?: string;
  workspacePath?: string;
};

const DIAGRAM_LANGS = new Set(["mermaid", "drawio", "diagrams", "diagrams.net", "mxfile", "echarts"]);

const MUTATION_TOOLS = new Set([
  "write_file",
  "edit_file",
  "apply_patch",
  "delete_file",
  "run_shell",
  "run_code",
]);

export function extractDiagramFences(markdown: string): DiagramFence[] {
  const src = String(markdown || "");
  const out: DiagramFence[] = [];
  const re = /```([a-zA-Z0-9._-]*)\s*\n([\s\S]*?)```/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(src))) {
    const lang = String(m[1] || "").trim().toLowerCase() || "text";
    if (!DIAGRAM_LANGS.has(lang) && !(lang === "xml" && /<(mxfile|mxGraphModel)\b/i.test(m[2] || ""))) {
      continue;
    }
    out.push({ lang: lang === "xml" ? "drawio" : lang, body: String(m[2] || "").trim() });
  }
  return out;
}

export function isMutationTool(name: string | undefined | null): boolean {
  const n = String(name || "").trim().toLowerCase();
  if (!n) return false;
  if (MUTATION_TOOLS.has(n)) return true;
  return /^(write|edit|apply|delete)_/.test(n) || n.includes("write_file") || n.includes("edit_file");
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function countLines(text: string): number {
  if (!text) return 0;
  return text.split(/\r\n|\n|\r/).length;
}

/** One-line human summary from tool args + result (path, bytes, replacements, snippet). */
export function summarizeMutationDetail(
  name: string,
  args: unknown,
  result: unknown,
): string {
  const a = asRecord(args) || {};
  const r = asRecord(result) || {};
  const path = String(a.path || a.file || a.filepath || a.target || r.path || "").trim();
  const bits: string[] = [];

  if (name === "write_file" || name.includes("write")) {
    const content = typeof a.content === "string" ? a.content : "";
    const bytes = Number(r.bytes ?? (content ? new TextEncoder().encode(content).length : 0));
    const created = r.created === true;
    const lines = content ? countLines(content) : 0;
    if (created) bits.push("created");
    else bits.push("overwrite");
    if (bytes > 0) bits.push(`${bytes} B`);
    if (lines > 0) bits.push(`${lines} lines`);
  } else if (name === "edit_file" || name.includes("edit")) {
    const reps = Number(r.replacements ?? (a.replace_all ? "n" : 1));
    const oldS = typeof a.old_string === "string" ? a.old_string : "";
    const newS = typeof a.new_string === "string" ? a.new_string : "";
    const oldLines = countLines(oldS);
    const newLines = countLines(newS);
    bits.push(`${reps}× replace`);
    if (oldLines || newLines) bits.push(`${oldLines}→${newLines} lines`);
    const tip = (newS || oldS).replace(/\s+/g, " ").trim().slice(0, 48);
    if (tip) bits.push(`“${tip}${tip.length >= 48 ? "…" : ""}”`);
  } else if (name === "delete_file" || name.includes("delete")) {
    bits.push("deleted");
  } else if (name === "run_shell" || name === "run_code") {
    const cmd = String(a.command || a.code || "").replace(/\s+/g, " ").trim().slice(0, 60);
    if (cmd) bits.push(cmd);
    const code = r.exit_code ?? r.returncode;
    if (code != null) bits.push(`exit ${code}`);
  } else if (name === "apply_patch") {
    bits.push("patch");
  }

  const pathPart = path ? `\`${path}\`` : "";
  const detail = bits.length ? bits.join(" · ") : "";
  if (pathPart && detail) return `${pathPart} — ${detail}`;
  return pathPart || detail || "";
}

export function summarizeMutationCalls(
  rows: Array<{
    tool_name?: string;
    success?: boolean;
    duration_ms?: number;
    arguments?: unknown;
    result?: unknown;
    error?: string | null;
  }>,
): string[] {
  const lines: string[] = [];
  for (const row of rows || []) {
    const name = String(row.tool_name || "").trim();
    if (!isMutationTool(name)) continue;
    const ok = row.success !== false && !row.error;
    const ms = row.duration_ms != null ? ` · ${Math.round(Number(row.duration_ms))}ms` : "";
    const detail = summarizeMutationDetail(name, row.arguments, row.result);
    const status = ok ? "OK" : `FAIL${row.error ? `: ${row.error}` : ""}`;
    if (detail) {
      lines.push(`- \`${name}\` ${detail} — **${status}**${ms}`);
    } else {
      lines.push(`- \`${name}\` — **${status}**${ms}`);
    }
  }
  return lines;
}

export function planTitleFromMarkdown(plan: string, fallback = "Delivery"): string {
  const m = String(plan || "").match(/^#\s+(.+)$/m);
  if (m?.[1]) return m[1].trim().slice(0, 80);
  const line = String(plan || "")
    .split("\n")
    .map((l) => l.trim())
    .find((l) => l && !l.startsWith("```"));
  return (line || fallback).slice(0, 80);
}

export function buildDeliveryMarkdown(
  seed: DeliverySeed,
  mutationLines: string[] = [],
): string {
  const acceptedAt = seed.acceptedAt || new Date().toISOString();
  const title = planTitleFromMarkdown(seed.plan, seed.title || "Delivery");
  const diagrams = extractDiagramFences(seed.plan);
  const parts: string[] = [
    `# Delivery · ${title}`,
    "",
    `- accepted_at: \`${acceptedAt}\``,
  ];
  if (seed.sessionId) parts.push(`- session_id: \`${seed.sessionId}\``);
  if (seed.callId) parts.push(`- call_id: \`${seed.callId}\``);
  if (seed.workspacePath) parts.push(`- workspace_file: \`${seed.workspacePath}\``);
  parts.push("", "## Plan", "", seed.plan.trim() || "_(empty plan)_", "");

  parts.push("## Diagrams", "");
  if (!diagrams.length) {
    parts.push("_(no diagram fences in plan)_", "");
  } else {
    diagrams.forEach((d, i) => {
      parts.push(`### ${d.lang} ${i + 1}`, "", "```" + d.lang, d.body, "```", "");
    });
  }

  parts.push("## Code changes", "");
  if (!mutationLines.length) {
    parts.push("_(no write/edit tools yet — will fill as the agent executes)_", "");
  } else {
    parts.push(...mutationLines, "");
  }

  parts.push(
    "## Links",
    "",
    "This Delivery artifact chains **Plan → Diagrams → Mutations** for audit.",
    "Also written under `.nlm/deliveries/` when a local workspace is bound.",
    "",
  );
  return parts.join("\n");
}

export function deliveryFileName(title: string, when = new Date()): string {
  const safe = String(title || "Delivery")
    .replace(/[^\w\u4e00-\u9fff.-]+/g, "_")
    .slice(0, 40);
  const stamp = when.toISOString().replace(/[:.]/g, "-").slice(0, 19);
  return `Delivery-${safe}-${stamp}.md`;
}
