/** Bounded plain-text preview for trajectory ledger rows (DSH-inspired). */

const PREVIEW_SOURCE_CHARS = 2_048;
const PREVIEW_OUTPUT_CHARS = 512;

/** Strip light Markdown noise without a full parser. */
export function trajectoryPreviewText(text: string): string {
  const raw = String(text || "");
  if (!raw) return "";
  const source = raw.slice(0, PREVIEW_SOURCE_CHARS);
  const compact = source
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/!\[[^\]]*\]\([^)]*\)/g, " ")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/^#{1,6}\s+/gm, "")
    .replace(/[*_~>|-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  const preview = compact.slice(0, PREVIEW_OUTPUT_CHARS).trimEnd();
  return source.length < raw.length || preview.length < compact.length
    ? `${preview}…`
    : preview;
}
