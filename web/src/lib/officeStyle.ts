/** Office style packs — keep tokens in sync with office_style.py */

export type OfficeStyleId = "commercial" | "academic";

export const DEFAULT_OFFICE_STYLE: OfficeStyleId = "commercial";

export type OfficeThemeTokens = {
  accent: string;
  accent_dark: string;
  ink: string;
  ink_soft: string;
  paper: string;
  paper_alt: string;
  muted: string;
  rule: string;
  quote_bg: string;
  header_fg: string;
  font_heading: string;
  font_body: string;
  font_east_asia: string;
  font_heading_east_asia: string;
};

export type OfficeLayoutFlags = {
  page_margin_in: number;
  page_margin_top_in: number;
  page_margin_bottom_in: number;
  line_spacing: number;
  body_size_pt: number;
  h1_size_pt: number;
  h2_size_pt: number;
  h3_size_pt: number;
  h1_underline: "thick" | "thin" | "none";
  h2_color: string;
  h3_color: string;
  quote_bar: "accent" | "hairline" | "none";
  quote_bar_sz: string;
  quote_shade: boolean;
  table_header_fill: boolean;
  table_zebra: boolean;
  equation_size_pt: number;
  equation_frame: boolean;
  equation_numbers: boolean;
  caption_numbers: boolean;
  word_header_title: boolean;
  word_footer_page: boolean;
  ppt_top_bar: boolean;
  ppt_section_fill: "dark" | "plain";
  ppt_section_number: boolean;
  ppt_title_size: number;
  ppt_heading_size: number;
  ppt_body_size: number;
  ppt_rule: boolean;
  ppt_quote_bar: boolean;
  ppt_footer_on_section: boolean;
};

export type OfficeStylePack = {
  id: OfficeStyleId;
  label: string;
  theme: OfficeThemeTokens;
  layout: OfficeLayoutFlags;
};

const COMMERCIAL_THEME: OfficeThemeTokens = {
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
  font_heading: "Calibri",
  font_body: "Calibri",
  font_east_asia: "微软雅黑",
  font_heading_east_asia: "微软雅黑",
};

const ACADEMIC_THEME: OfficeThemeTokens = {
  accent: "#1B365D",
  accent_dark: "#12243F",
  ink: "#1A1A1A",
  ink_soft: "#2C2C2C",
  paper: "#FFFFFF",
  paper_alt: "#FFFFFF",
  muted: "#555555",
  rule: "#C8C8C8",
  quote_bg: "#FFFFFF",
  header_fg: "#1A1A1A",
  font_heading: "Times New Roman",
  font_body: "Times New Roman",
  font_east_asia: "宋体",
  font_heading_east_asia: "黑体",
};

const COMMERCIAL_LAYOUT: OfficeLayoutFlags = {
  page_margin_in: 0.95,
  page_margin_top_in: 0.9,
  page_margin_bottom_in: 0.85,
  line_spacing: 1.35,
  body_size_pt: 11,
  h1_size_pt: 26,
  h2_size_pt: 16,
  h3_size_pt: 13,
  h1_underline: "thick",
  h2_color: "accent_dark",
  h3_color: "ink_soft",
  quote_bar: "accent",
  quote_bar_sz: "24",
  quote_shade: true,
  table_header_fill: true,
  table_zebra: true,
  equation_size_pt: 14,
  equation_frame: true,
  equation_numbers: false,
  caption_numbers: false,
  word_header_title: false,
  word_footer_page: false,
  ppt_top_bar: true,
  ppt_section_fill: "dark",
  ppt_section_number: false,
  ppt_title_size: 40,
  ppt_heading_size: 26,
  ppt_body_size: 20,
  ppt_rule: true,
  ppt_quote_bar: true,
  ppt_footer_on_section: false,
};

const ACADEMIC_LAYOUT: OfficeLayoutFlags = {
  page_margin_in: 1.25,
  page_margin_top_in: 1.15,
  page_margin_bottom_in: 1.1,
  line_spacing: 1.55,
  body_size_pt: 12,
  h1_size_pt: 16,
  h2_size_pt: 14,
  h3_size_pt: 12,
  h1_underline: "thin",
  h2_color: "ink",
  h3_color: "ink",
  quote_bar: "hairline",
  quote_bar_sz: "6",
  quote_shade: false,
  table_header_fill: false,
  table_zebra: false,
  equation_size_pt: 12,
  equation_frame: false,
  equation_numbers: true,
  caption_numbers: true,
  word_header_title: true,
  word_footer_page: true,
  ppt_top_bar: false,
  ppt_section_fill: "plain",
  ppt_section_number: true,
  ppt_title_size: 32,
  ppt_heading_size: 22,
  ppt_body_size: 18,
  ppt_rule: true,
  ppt_quote_bar: false,
  ppt_footer_on_section: true,
};

export const OFFICE_STYLE_PACKS: Record<OfficeStyleId, OfficeStylePack> = {
  commercial: {
    id: "commercial",
    label: "商业风",
    theme: COMMERCIAL_THEME,
    layout: COMMERCIAL_LAYOUT,
  },
  academic: {
    id: "academic",
    label: "学术风",
    theme: ACADEMIC_THEME,
    layout: ACADEMIC_LAYOUT,
  },
};

const STYLE_ALIASES: Record<string, OfficeStyleId> = {
  commercial: "commercial",
  business: "commercial",
  biz: "commercial",
  商务: "commercial",
  商业: "commercial",
  商业风: "commercial",
  academic: "academic",
  paper: "academic",
  scholar: "academic",
  学术: "academic",
  学术风: "academic",
};

export function normalizeOfficeStyleId(raw?: string | null): OfficeStyleId {
  const text = String(raw || "").trim().toLowerCase();
  if (!text) return DEFAULT_OFFICE_STYLE;
  return STYLE_ALIASES[text] || DEFAULT_OFFICE_STYLE;
}

export function themeFromStyle(styleId?: string | null): OfficeThemeTokens {
  return { ...OFFICE_STYLE_PACKS[normalizeOfficeStyleId(styleId)].theme };
}

export function layoutFromStyle(styleId?: string | null): OfficeLayoutFlags {
  return { ...OFFICE_STYLE_PACKS[normalizeOfficeStyleId(styleId)].layout };
}

export function officeThemeCssVars(theme: Partial<OfficeThemeTokens>): Record<string, string> {
  const t = { ...COMMERCIAL_THEME, ...theme };
  return {
    "--office-accent": t.accent,
    "--office-accent-dark": t.accent_dark,
    "--office-ink": t.ink,
    "--office-ink-soft": t.ink_soft,
    "--office-paper": t.paper,
    "--office-paper-alt": t.paper_alt,
    "--office-muted": t.muted,
    "--office-rule": t.rule,
    "--office-quote-bg": t.quote_bg,
    "--office-header-fg": t.header_fg,
    "--office-font-heading": `"${t.font_heading}", "${t.font_heading_east_asia}", "IBM Plex Sans", "PingFang SC", sans-serif`,
    "--office-font-body": `"${t.font_body}", "${t.font_east_asia}", "IBM Plex Sans", "PingFang SC", sans-serif`,
  };
}

export function formatOfficeCaption(
  kind: "图" | "表",
  n: number,
  caption: string | undefined,
  numbered: boolean,
): string {
  const text = String(caption || "").trim();
  if (!numbered) return text;
  if (text && /^(图|表|Figure|Table)\b/i.test(text)) return text;
  const prefix = `${kind} ${n}`;
  return text ? `${prefix}  ${text}` : prefix;
}
