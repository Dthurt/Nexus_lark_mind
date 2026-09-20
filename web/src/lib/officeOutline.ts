/** Shared Office outline — keep fields in sync with office_outline.py */

export const OFFICE_SCHEMA = "nlm.office.v1";

export const OFFICE_THEME = {
  accent: "#2A9D8F",
  accent_dark: "#1D7A70",
  ink: "#1C2430",
  ink_soft: "#3D4A57",
  paper: "#F6F3EC",
  paper_alt: "#EFEBE3",
  muted: "#5C6B7A",
  rule: "#C9D4CE",
  quote_bg: "#E4F2EE",
  header_fg: "#F6F3EC",
} as const;

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
  theme?: Partial<typeof OFFICE_THEME>;
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
      latex: String(b.latex || b.tex || b.math || b.text || b.content || ""),
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
      latex: String(s.latex || s.tex || s.math || s.text || s.content || ""),
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
  return {
    schema: OFFICE_SCHEMA,
    doc_id: String(raw.doc_id || ""),
    kind,
    title: String(raw.title || ""),
    subtitle: raw.subtitle || "",
    author: raw.author || "",
    theme: { ...OFFICE_THEME, ...(raw.theme || {}) },
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
