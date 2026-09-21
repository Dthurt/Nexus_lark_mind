/** Shared Office outline — keep fields in sync with office_outline.py */

import {
  DEFAULT_OFFICE_STYLE,
  normalizeOfficeStyleId,
  themeFromStyle,
  type OfficeStyleId,
  type OfficeThemeTokens,
} from "@/lib/officeStyle";

export const OFFICE_SCHEMA = "nlm.office.v1";

export const OFFICE_THEME = themeFromStyle(DEFAULT_OFFICE_STYLE);

export type { OfficeStyleId, OfficeThemeTokens };

export type OfficeKind = "docx" | "pptx";

export type OfficePlanItem = {
  id: string;
  title: string;
  maps_to?: string;
  status?: "pending" | "done" | "writing" | string;
  filled?: boolean;
};

export type OfficeGlossaryItem = {
  term: string;
  meaning?: string;
};

export type OfficeVoice = {
  tone?: string;
  person?: string;
  tense?: string;
};

export type OfficeLastBlock = {
  heading?: string;
  excerpt?: string;
  plan_id?: string;
};

export type OfficeRequirement = {
  id: string;
  text: string;
  mapped_to?: string;
  filled?: boolean;
};

export type OfficeWordBlock =
  | { id: string; type: "heading"; level: 1 | 2 | 3; text: string; req?: string }
  | { id: string; type: "paragraph"; text: string; req?: string }
  | { id: string; type: "bullet_list"; items: string[]; req?: string }
  | { id: string; type: "numbered_list"; items: string[]; req?: string }
  | { id: string; type: "quote"; text: string; attribution?: string; req?: string }
  | { id: string; type: "table"; headers: string[]; rows: string[][]; req?: string }
  | { id: string; type: "page_break"; req?: string }
  | {
      id: string;
      type: "image";
      path?: string;
      url?: string;
      caption?: string;
      alt?: string;
      preview_url?: string;
      req?: string;
    }
  | {
      id: string;
      type: "equation";
      latex: string;
      display?: "inline" | "block";
      caption?: string;
      text?: string;
      req?: string;
    };

export type OfficeColumn = { heading?: string; body?: string; items?: string[] };

export type OfficeSlide =
  | { id: string; type: "title"; title: string; subtitle?: string; notes?: string; req?: string }
  | { id: string; type: "section"; title: string; kicker?: string; notes?: string; req?: string }
  | { id: string; type: "bullets"; title: string; items: string[]; notes?: string; req?: string }
  | {
      id: string;
      type: "two_column";
      title: string;
      left?: OfficeColumn;
      right?: OfficeColumn;
      notes?: string;
      req?: string;
    }
  | { id: string; type: "quote"; text: string; attribution?: string; notes?: string; req?: string }
  | {
      id: string;
      type: "image";
      title?: string;
      path?: string;
      url?: string;
      caption?: string;
      preview_url?: string;
      notes?: string;
      req?: string;
    }
  | {
      id: string;
      type: "equation";
      title?: string;
      latex: string;
      caption?: string;
      text?: string;
      notes?: string;
      req?: string;
    };

export type OfficeOutline = {
  schema?: string;
  doc_id: string;
  kind: OfficeKind;
  title: string;
  subtitle?: string;
  author?: string;
  style_id?: OfficeStyleId | string;
  theme?: Partial<OfficeThemeTokens>;
  throughline?: string;
  thesis?: string;
  voice?: OfficeVoice;
  glossary?: OfficeGlossaryItem[];
  terms?: OfficeGlossaryItem[];
  forbidden?: string[];
  last_block?: OfficeLastBlock;
  plan?: OfficePlanItem[];
  requirements?: OfficeRequirement[];
  blocks?: OfficeWordBlock[];
  slides?: OfficeSlide[];
  status?: string;
  writing?: boolean;
  last_op?: string;
  last_ids?: string[];
  file_name?: string;
  path?: string;
  download_url?: string;
};

export const NLM_OFFICE_WRITING_EVENT = "nlm-office-writing";

export function emptyOfficeOutline(): OfficeOutline {
  return {
    schema: OFFICE_SCHEMA,
    doc_id: "",
    kind: "docx",
    title: "",
    style_id: DEFAULT_OFFICE_STYLE,
    theme: themeFromStyle(DEFAULT_OFFICE_STYLE),
    throughline: "",
    glossary: [],
    forbidden: [],
    last_block: {},
    plan: [],
    requirements: [],
    blocks: [],
    slides: [],
    last_ids: [],
  };
}

export function parseOfficeOutline(raw: string | OfficeOutline | null | undefined): OfficeOutline | null {
  if (!raw) return null;
  if (typeof raw === "object") {
    if (!raw.kind && !raw.doc_id && !raw.blocks && !raw.slides) return null;
    return normalizeOutline(raw);
  }
  const text = String(raw).trim();
  if (!text) return null;
  try {
    const data = JSON.parse(text);
    if (!data || typeof data !== "object") return null;
    return normalizeOutline(data as OfficeOutline);
  } catch {
    return null;
  }
}

function asList(value: unknown): unknown[] {
  if (value == null) return [];
  return Array.isArray(value) ? value : [value];
}

export function officeTextHasMath(text: string | undefined | null): boolean {
  const raw = String(text || "");
  return /\$\$|\\\(|\\\[|(?<!\$)\$(?!\$)|\\begin\{(?:equation|align)/.test(raw);
}

const OFFICE_MATH_RE =
  /\$\$([\s\S]+?)\$\$|\\\[([\s\S]+?)\\\]|\\begin\{(?:equation|align|alignat|gather|multline|displaymath|eqnarray)\*?\}([\s\S]+?)\\end\{(?:equation|align|alignat|gather|multline|displaymath|eqnarray)\*?\}|\\\(([\s\S]+?)\\\)|(?<!\$)\$(?!\$)((?:\\.|[^$\n\\])+?)\$(?!\$)/g;

export type OfficeMathPart = { kind: "text" | "math"; value: string };

export function unwrapOfficeLatex(raw: string): string {
  const s = String(raw || "").trim();
  if (!s) return "";
  const patterns = [/^\$\$([\s\S]*)\$\$$/, /^\\\[([\s\S]*)\\\]$/, /^\\\(([\s\S]*)\\\)$/, /^\$([\s\S]*)\$$/];
  for (const re of patterns) {
    const m = s.match(re);
    if (m) return String(m[1] || "").trim();
  }
  return s;
}

export function splitOfficeMath(text: string): OfficeMathPart[] {
  const raw = String(text || "");
  if (!raw) return [];
  const parts: OfficeMathPart[] = [];
  const re = new RegExp(OFFICE_MATH_RE.source, "g");
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(raw)) !== null) {
    if (m.index > last) parts.push({ kind: "text", value: raw.slice(last, m.index) });
    const latex = unwrapOfficeLatex(String(m[1] || m[2] || m[3] || m[4] || m[5] || "").trim());
    if (latex) parts.push({ kind: "math", value: latex });
    last = m.index + m[0].length;
  }
  if (last < raw.length) parts.push({ kind: "text", value: raw.slice(last) });
  if (!parts.length) parts.push({ kind: "text", value: raw });
  return parts;
}

const HARD_LATEX = /\\(begin|end|align|alignat|gather|multline|matrix|pmatrix|bmatrix|vmatrix|cases|split|substack)\b/;

function outlineMathTexts(outline: OfficeOutline): string[] {
  const out: string[] = [];
  const push = (value?: string) => {
    const text = String(value || "").trim();
    if (text) out.push(text);
  };
  for (const block of outline.blocks || []) {
    if ("text" in block) push(block.text);
    if ("latex" in block) push(block.latex);
    if ("items" in block && Array.isArray(block.items)) {
      for (const item of block.items) push(item);
    }
  }
  for (const slide of outline.slides || []) {
    push("title" in slide ? slide.title : "");
    push("subtitle" in slide ? slide.subtitle : "");
    push("text" in slide ? slide.text : "");
    if ("latex" in slide) push(slide.latex);
    if ("items" in slide && Array.isArray(slide.items)) {
      for (const item of slide.items) push(item);
    }
    if (slide.type === "two_column") {
      push(slide.left?.body);
      push(slide.right?.body);
      for (const item of slide.left?.items || []) push(item);
      for (const item of slide.right?.items || []) push(item);
    }
  }
  return out;
}

export function officeMathExportHints(outline: OfficeOutline): string[] {
  const texts = outlineMathTexts(outline);
  const hasMath = texts.some(
    (text) => splitOfficeMath(text).some((part) => part.kind === "math") || HARD_LATEX.test(text),
  );
  if (!hasMath) return [];
  if (outline.kind === "pptx") {
    const hints = ["PPT 导出的是 Cambria Math 文本，不是 PowerPoint 可编辑公式。"];
    if (texts.some((text) => HARD_LATEX.test(text))) {
      hints.push("含 align/matrix 等环境，下载后可能对不齐。");
    }
    return hints;
  }
  if (texts.some((text) => HARD_LATEX.test(text))) {
    return ["部分公式 Word 可能降级为普通文本，画布预览会更好看。"];
  }
  return [];
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : null;
}

function normalizeBlock(raw: unknown): OfficeWordBlock | null {
  const b = asRecord(raw);
  if (!b) return null;
  const id = String(b.id || "");
  const type = String(b.type || b.kind || "").toLowerCase();
  const req = b.req != null ? String(b.req) : undefined;
  if (type === "math" || type === "equation" || type === "latex" || type === "formula") {
    return {
      id,
      type: "equation",
      latex: unwrapOfficeLatex(String(b.latex || b.tex || b.math || b.text || b.content || "")),
      display: String(b.display || "block") === "inline" ? "inline" : "block",
      caption: b.caption != null ? String(b.caption) : undefined,
      text: b.text != null ? String(b.text) : undefined,
      req,
    };
  }
  return raw as OfficeWordBlock;
}

function normalizeSlide(raw: unknown): OfficeSlide | null {
  const s = asRecord(raw);
  if (!s) return null;
  const type = String(s.type || s.kind || s.layout || "").toLowerCase();
  if (type === "math" || type === "equation" || type === "latex" || type === "formula") {
    return {
      id: String(s.id || ""),
      type: "equation",
      title: s.title != null ? String(s.title) : undefined,
      latex: unwrapOfficeLatex(String(s.latex || s.tex || s.math || s.text || s.content || "")),
      caption: s.caption != null ? String(s.caption) : undefined,
      text: s.text != null ? String(s.text) : undefined,
      notes: s.notes != null ? String(s.notes) : undefined,
      req: s.req != null ? String(s.req) : undefined,
    };
  }
  return raw as OfficeSlide;
}

function normalizeOutline(raw: OfficeOutline): OfficeOutline {
  const kind = String(raw.kind || (raw.slides?.length ? "pptx" : "docx")).toLowerCase() === "pptx" ? "pptx" : "docx";
  const glossarySrc = (raw.glossary || raw.terms || []) as OfficeGlossaryItem[];
  const styleId = normalizeOfficeStyleId(raw.style_id);
  return {
    schema: OFFICE_SCHEMA,
    doc_id: String(raw.doc_id || ""),
    kind,
    title: String(raw.title || ""),
    subtitle: raw.subtitle || "",
    author: raw.author || "",
    style_id: styleId,
    theme: themeFromStyle(styleId),
    throughline: String(raw.throughline || raw.thesis || ""),
    voice: raw.voice || {},
    glossary: glossarySrc.map((row) => ({
      term: String(row.term || ""),
      meaning: row.meaning || "",
    })),
    forbidden: (raw.forbidden || []).map(String),
    last_block: raw.last_block || {},
    plan: (raw.plan || []).map((row, i) => ({
      id: String(row.id || `p${i + 1}`),
      title: String(row.title || ""),
      maps_to: row.maps_to || "",
      status: row.status || (row.filled ? "done" : "pending"),
      filled: !!row.filled || row.status === "done",
    })),
    requirements: (raw.requirements || []).map((row, i) => ({
      id: String(row.id || `r${i + 1}`),
      text: String(row.text || ""),
      mapped_to: row.mapped_to || "",
      filled: !!row.filled,
    })),
    blocks: (raw.blocks || []).map(normalizeBlock).filter((b): b is OfficeWordBlock => !!b),
    slides: (raw.slides || []).map(normalizeSlide).filter((s): s is OfficeSlide => !!s),
    status: raw.status || "",
    writing: !!raw.writing,
    last_op: raw.last_op || "",
    last_ids: (raw.last_ids || []).map(String),
    file_name: raw.file_name || "",
    path: raw.path || "",
    download_url: raw.download_url || "",
  };
}

export function collectOfficeIds(outline: OfficeOutline | null): string[] {
  if (!outline) return [];
  const ids: string[] = [];
  for (const b of outline.blocks || []) if (b.id) ids.push(b.id);
  for (const s of outline.slides || []) if (s.id) ids.push(s.id);
  return ids;
}

export function officeAlignment(outline: OfficeOutline): {
  plan: OfficePlanItem[];
  requirements: OfficeRequirement[];
  filledPlan: number;
  totalPlan: number;
} {
  const titles: string[] = [];
  const reqs = new Set<string>();
  for (const b of outline.blocks || []) {
    if (b.req) reqs.add(b.req);
    if (b.type === "heading") titles.push(b.text);
  }
  for (const s of outline.slides || []) {
    if (s.req) reqs.add(s.req);
    const t = "title" in s ? s.title : "text" in s ? s.text : "";
    if (t) titles.push(t);
  }
  const covered = (id: string, title: string, status?: string) => {
    if (status === "done") return true;
    if (id && reqs.has(id)) return true;
    if (title && titles.some((t) => t.includes(title) || title.includes(t))) return true;
    return false;
  };
  const plan = (outline.plan || []).map((row) => ({
    ...row,
    filled: covered(row.id, row.title, row.status),
  }));
  const requirements = (outline.requirements || []).map((row) => ({
    ...row,
    filled: !!(row.mapped_to && reqs.has(row.mapped_to)) || covered(row.id, row.text),
  }));
  return {
    plan,
    requirements,
    filledPlan: plan.filter((p) => p.filled).length,
    totalPlan: plan.length,
  };
}

export function officeImageSrc(item: { preview_url?: string; url?: string; path?: string }): string {
  return String(item.preview_url || item.url || "").trim();
}

export { asList };
