/**
 * Line-oriented diff for tool-card file changes (Claude Code style).
 * Prefer a small LCS so edits show as −old / +new rather than whole-file rewrite.
 */

function splitLines(text: any) {
  if (text == null) return [];
  const s = String(text);
  if (s === "") return [""];
  return s.split("\n");
}

/** Myers-inspired O(ND) is overkill; LCS DP is fine for typical edit hunks. */
function lcsTable(a: string[], b: string[]) {
  const n = a.length;
  const m = b.length;
  // Cap to avoid huge matrices on accidental full-file dumps
  if (n * m > 250_000) return null;
  const dp = Array.from({ length: n + 1 }, () => new Uint16Array(m + 1));
  for (let i = 1; i <= n; i += 1) {
    for (let j = 1; j <= m; j += 1) {
      dp[i][j] = a[i - 1] === b[j - 1] ? dp[i - 1][j - 1] + 1 : Math.max(dp[i - 1][j], dp[i][j - 1]);
    }
  }
  return dp;
}

function backtrack(dp: Uint16Array[], a: string[], b: string[]) {
  const rows: any[] = [];
  let i = a.length;
  let j = b.length;
  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && a[i - 1] === b[j - 1]) {
      rows.push({ type: "ctx", text: a[i - 1], oldLine: i, newLine: j });
      i -= 1;
      j -= 1;
    } else if (j > 0 && (i === 0 || dp[i][j - 1] >= dp[i - 1][j])) {
      rows.push({ type: "add", text: b[j - 1], oldLine: null, newLine: j });
      j -= 1;
    } else {
      rows.push({ type: "del", text: a[i - 1], oldLine: i, newLine: null });
      i -= 1;
    }
  }
  rows.reverse();
  return rows;
}

/** Fallback when LCS would be too large: show all dels then all adds. */
function naiveReplace(a: string[], b: string[]) {
  const rows: any[] = [];
  for (let i = 0; i < a.length; i += 1) {
    rows.push({ type: "del", text: a[i], oldLine: i + 1, newLine: null });
  }
  for (let j = 0; j < b.length; j += 1) {
    rows.push({ type: "add", text: b[j], oldLine: null, newLine: j + 1 });
  }
  return rows;
}

export function lineDiff(oldText: any, newText: any) {
  const a = splitLines(oldText);
  const b = splitLines(newText);
  // Identical
  if (a.length === b.length && a.every((line, i) => line === b[i])) {
    return {
      rows: a.map((text, i) => ({ type: "ctx", text, oldLine: i + 1, newLine: i + 1 })),
      stats: { adds: 0, dels: 0, ctx: a.length },
    };
  }
  const dp = lcsTable(a, b);
  const rows = dp ? backtrack(dp, a, b) : naiveReplace(a, b);
  let adds = 0;
  let dels = 0;
  let ctx = 0;
  for (const r of rows) {
    if (r.type === "add") adds += 1;
    else if (r.type === "del") dels += 1;
    else ctx += 1;
  }
  return { rows, stats: { adds, dels, ctx } };
}

/** New file / overwrite: treat entire content as additions. */
export function writeFileAsDiff(content: any) {
  const lines = splitLines(content);
  const rows = lines.map((text: string, i: number) => ({
    type: "add",
    text,
    oldLine: null,
    newLine: i + 1,
  }));
  return { rows, stats: { adds: rows.length, dels: 0, ctx: 0 } };
}

export function formatDiffStats(stats: any) {
  const a = Number(stats?.adds || 0);
  const d = Number(stats?.dels || 0);
  if (!a && !d) return "无变更";
  const parts: string[] = [];
  if (a) parts.push(`+${a}`);
  if (d) parts.push(`−${d}`);
  return parts.join(" ");
}
