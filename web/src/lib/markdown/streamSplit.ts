/**
 * Split streaming markdown into a stable prefix (safe to parse) and a growing tail
 * (kept as plain text until the next block boundary closes).
 */
export function splitSettledMarkdown(text: string): { settled: string; tail: string } {
  const src = String(text || "");
  if (!src) return { settled: "", tail: "" };

  const lines = src.split("\n");
  let inFence = false;
  let fenceChar = "";
  let fenceLen = 0;
  let fenceOpenLine = -1;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const m = /^( {0,3})(`{3,}|~{3,})(.*)$/.exec(line);
    if (!m) continue;
    const marker = m[2];
    const ch = marker[0];
    const len = marker.length;
    const info = (m[3] || "").trim();
    if (!inFence) {
      inFence = true;
      fenceChar = ch;
      fenceLen = len;
      fenceOpenLine = i;
    } else if (ch === fenceChar && len >= fenceLen && !info) {
      inFence = false;
      fenceOpenLine = -1;
    }
  }

  if (inFence && fenceOpenLine >= 0) {
    let cut = 0;
    for (let i = 0; i < fenceOpenLine; i++) {
      cut += lines[i].length + 1;
    }
    return { settled: src.slice(0, cut), tail: src.slice(cut) };
  }

  // Prefer paragraph boundary so lists/headings don't reflow mid-block.
  const para = src.lastIndexOf("\n\n");
  if (para >= 0) {
    return {
      settled: src.slice(0, para + 2),
      tail: src.slice(para + 2),
    };
  }

  // Otherwise settle complete lines; keep the unfinished last line as tail.
  const lastNl = src.lastIndexOf("\n");
  if (lastNl >= 0) {
    return {
      settled: src.slice(0, lastNl + 1),
      tail: src.slice(lastNl + 1),
    };
  }

  return { settled: "", tail: src };
}
