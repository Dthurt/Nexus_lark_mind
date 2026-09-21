"""Office style packs — colors/fonts plus layout flags.

LLM stays style-blind. Scripts expand a pack onto the outline after write.
Keep tokens in sync with web/src/lib/officeStyle.ts.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping

STYLE_IDS = ("commercial", "academic")
DEFAULT_STYLE_ID = "commercial"

# Commercial = current product look (no visual regression when style_id is missing).
COMMERCIAL_THEME: Dict[str, str] = {
    "accent": "#2A9D8F",
    "accent_dark": "#1D7A70",
    "ink": "#1C2430",
    "ink_soft": "#3D4A57",
    "paper": "#F6F3EC",
    "paper_alt": "#EFEBE3",
    "muted": "#5C6B7A",
    "rule": "#C9D4CE",
    "quote_bg": "#E4F2EE",
    "header_fg": "#F6F3EC",
    "font_heading": "Calibri",
    "font_body": "Calibri",
    "font_east_asia": "微软雅黑",
    "font_heading_east_asia": "微软雅黑",
}

ACADEMIC_THEME: Dict[str, str] = {
    "accent": "#1B365D",
    "accent_dark": "#12243F",
    "ink": "#1A1A1A",
    "ink_soft": "#2C2C2C",
    "paper": "#FFFFFF",
    "paper_alt": "#FFFFFF",
    "muted": "#555555",
    "rule": "#C8C8C8",
    "quote_bg": "#FFFFFF",
    "header_fg": "#1A1A1A",
    "font_heading": "Times New Roman",
    "font_body": "Times New Roman",
    "font_east_asia": "宋体",
    "font_heading_east_asia": "黑体",
}

COMMERCIAL_LAYOUT: Dict[str, Any] = {
    "page_margin_in": 0.95,
    "page_margin_top_in": 0.9,
    "page_margin_bottom_in": 0.85,
    "line_spacing": 1.35,
    "body_size_pt": 11,
    "h1_size_pt": 26,
    "h2_size_pt": 16,
    "h3_size_pt": 13,
    "h1_underline": "thick",
    "h2_color": "accent_dark",
    "h3_color": "ink_soft",
    "quote_bar": "accent",
    "quote_bar_sz": "24",
    "quote_shade": True,
    "table_header_fill": True,
    "table_zebra": True,
    "equation_size_pt": 14,
    "equation_frame": True,
    "equation_numbers": False,
    "caption_numbers": False,
    "word_header_title": False,
    "word_footer_page": False,
    "ppt_top_bar": True,
    "ppt_section_fill": "dark",
    "ppt_section_number": False,
    "ppt_title_size": 40,
    "ppt_heading_size": 26,
    "ppt_body_size": 20,
    "ppt_rule": True,
    "ppt_quote_bar": True,
    "ppt_footer_on_section": False,
}

ACADEMIC_LAYOUT: Dict[str, Any] = {
    "page_margin_in": 1.25,
    "page_margin_top_in": 1.15,
    "page_margin_bottom_in": 1.1,
    "line_spacing": 1.55,
    "body_size_pt": 12,
    "h1_size_pt": 16,
    "h2_size_pt": 14,
    "h3_size_pt": 12,
    "h1_underline": "thin",
    "h2_color": "ink",
    "h3_color": "ink",
    "quote_bar": "hairline",
    "quote_bar_sz": "6",
    "quote_shade": False,
    "table_header_fill": False,
    "table_zebra": False,
    "equation_size_pt": 12,
    "equation_frame": False,
    "equation_numbers": True,
    "caption_numbers": True,
    "word_header_title": True,
    "word_footer_page": True,
    "ppt_top_bar": False,
    "ppt_section_fill": "plain",
    "ppt_section_number": True,
    "ppt_title_size": 32,
    "ppt_heading_size": 22,
    "ppt_body_size": 18,
    "ppt_rule": True,
    "ppt_quote_bar": False,
    "ppt_footer_on_section": True,
}

STYLE_PACKS: Dict[str, Dict[str, Any]] = {
    "commercial": {
        "id": "commercial",
        "label": "商业风",
        "theme": COMMERCIAL_THEME,
        "layout": COMMERCIAL_LAYOUT,
    },
    "academic": {
        "id": "academic",
        "label": "学术风",
        "theme": ACADEMIC_THEME,
        "layout": ACADEMIC_LAYOUT,
    },
}

# Alias used by outline + writer fallbacks (today's look).
DEFAULT_THEME: Dict[str, str] = dict(COMMERCIAL_THEME)

_STYLE_ALIASES = {
    "commercial": "commercial",
    "business": "commercial",
    "biz": "commercial",
    "商务": "commercial",
    "商业": "commercial",
    "商业风": "commercial",
    "academic": "academic",
    "paper": "academic",
    "scholar": "academic",
    "学术": "academic",
    "学术风": "academic",
}


def normalize_style_id(raw: Any) -> str:
    text = str(raw or "").strip().lower()
    if not text:
        return DEFAULT_STYLE_ID
    return _STYLE_ALIASES.get(text, DEFAULT_STYLE_ID)


def get_style_pack(style_id: Any) -> Dict[str, Any]:
    sid = normalize_style_id(style_id)
    return STYLE_PACKS[sid]


def theme_from_style(style_id: Any) -> Dict[str, str]:
    pack = get_style_pack(style_id)
    return dict(pack["theme"])


def layout_from_style(style_id: Any) -> Dict[str, Any]:
    pack = get_style_pack(style_id)
    return dict(pack["layout"])


def apply_style_to_outline(outline: Dict[str, Any], style_id: Any) -> Dict[str, Any]:
    """Set style_id and expand pack tokens. Does not render the binary."""
    sid = normalize_style_id(style_id)
    outline["style_id"] = sid
    outline["theme"] = theme_from_style(sid)
    return outline


def token_color(theme: Mapping[str, str], token: str, default: str = "") -> str:
    key = str(token or "").strip()
    if key.startswith("#"):
        return key
    return str(theme.get(key) or default or theme.get("ink") or "#1C2430")


def numbered_caption(kind: str, n: int, caption: str, *, enabled: bool) -> str:
    text = str(caption or "").strip()
    if not enabled:
        return text
    if text and (
        text.startswith("图")
        or text.startswith("表")
        or text.lower().startswith("figure")
        or text.lower().startswith("table")
    ):
        return text
    prefix = f"{kind} {n}"
    return f"{prefix}  {text}" if text else prefix
