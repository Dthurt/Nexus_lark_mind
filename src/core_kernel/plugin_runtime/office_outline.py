"""Office document outline — JSON source of truth for Word/PPT.

Preview (Canvas) and python-docx / python-pptx writers consume the SAME fields
so what the user sees is what they download.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from uuid import uuid4

from src.core_kernel.plugin_runtime.office_math import (
    extract_standalone_latex,
    latex_display,
    latex_from_block,
    strip_latex_wrappers,
)
from src.core_kernel.plugin_runtime.office_style import (
    DEFAULT_STYLE_ID,
    DEFAULT_THEME,
    normalize_style_id,
    theme_from_style,
)

# Re-export pack tokens so existing `from office_outline import DEFAULT_THEME` keeps working.
assert DEFAULT_THEME["accent"] == "#2A9D8F"

SCHEMA = "nlm.office.v1"

# DEFAULT_THEME is the commercial pack (today's look). Packs live in office_style.py.

WORD_BLOCK_TYPES = {
    "heading",
    "paragraph",
    "bullet_list",
    "numbered_list",
    "quote",
    "table",
    "page_break",
    "image",
    "equation",
}
PPT_SLIDE_TYPES = {"title", "section", "bullets", "two_column", "quote", "image", "equation"}
MAX_APPEND_BLOCKS = 8
MAX_APPEND_SLIDES = 3
DEFAULT_FORBIDDEN = [
    "不要复述封面或引言",
    "不要在更早章节未写完时提前写结论",
    "不要引入 plan 中不存在的新章节（先 office_revise_plan）",
    "术语以 glossary 为准，不要换名",
]
CONCLUSION_TITLES = {
    "结论",
    "总结",
    "结语",
    "小结",
    "收束",
    "下一步",
    "谢谢",
    "致谢",
    "conclusion",
    "summary",
    "wrap-up",
    "wrapup",
    "next steps",
    "thanks",
}
DEFAULT_VOICE = {
    "tone": "专业、克制、书面",
    "person": "第三人称",
    "tense": "一般现在",
}
COVER_HEADINGS = {"文档结构", "议程"}


class OfficeOutlineError(ValueError):
    """Invalid outline / tool payload."""


def new_doc_id() -> str:
    return f"off_{uuid4().hex[:12]}"


def new_item_id(prefix: str = "b") -> str:
    return f"{prefix}_{uuid4().hex[:8]}"


def normalize_kind(raw: Any) -> str:
    text = str(raw or "").strip().lower()
    if text in {"docx", "word", "doc", "文档", "word文档"}:
        return "docx"
    if text in {"pptx", "ppt", "powerpoint", "slides", "幻灯片", "演示", "ppt文档"}:
        return "pptx"
    raise OfficeOutlineError("kind must be docx (Word) or pptx (PowerPoint)")


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def normalize_theme(raw: Any = None, *, style_id: Any = "") -> Dict[str, str]:
    """Theme is owned by the style pack. Model-supplied colors/fonts are ignored."""
    del raw
    return theme_from_style(style_id)


def normalize_plan(raw: Any) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for i, item in enumerate(_as_list(raw), 1):
        if isinstance(item, str):
            title = item.strip()
            if not title:
                continue
            rows.append({"id": f"p{i}", "title": title, "maps_to": title, "status": "pending"})
            continue
        if not isinstance(item, dict):
            continue
        title = _clean_text(item.get("title") or item.get("text") or item.get("heading"))
        if not title:
            continue
        rid = _clean_text(item.get("id")) or f"p{i}"
        maps_to = _clean_text(item.get("maps_to") or item.get("requirement") or item.get("mapsTo"))
        status = _clean_text(item.get("status")).lower()
        if item.get("filled") is True:
            status = "done"
        if status not in {"pending", "done", "writing"}:
            status = "pending"
        rows.append({"id": rid, "title": title, "maps_to": maps_to or title, "status": status})
    return rows


def normalize_requirements(raw: Any) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for i, item in enumerate(_as_list(raw), 1):
        if isinstance(item, str):
            text = item.strip()
            if not text:
                continue
            rows.append({"id": f"r{i}", "text": text, "mapped_to": ""})
            continue
        if not isinstance(item, dict):
            continue
        text = _clean_text(item.get("text") or item.get("title") or item.get("requirement"))
        if not text:
            continue
        rid = _clean_text(item.get("id")) or f"r{i}"
        mapped = _clean_text(item.get("mapped_to") or item.get("mappedTo") or item.get("plan_id"))
        rows.append({"id": rid, "text": text, "mapped_to": mapped})
    return rows


def normalize_throughline(raw: Any, *, title: str = "", required: bool = False) -> str:
    text = _clean_text(raw)
    if not text and required:
        raise OfficeOutlineError(
            "office_create requires throughline (or thesis): one sentence that states the "
            "document's 系统观 / through-line before any body is written."
        )
    return text or _clean_text(title)


def normalize_voice(raw: Any) -> Dict[str, str]:
    voice = dict(DEFAULT_VOICE)
    if isinstance(raw, dict):
        for key in ("tone", "person", "tense"):
            val = _clean_text(raw.get(key))
            if val:
                voice[key] = val
    elif isinstance(raw, str) and raw.strip():
        voice["tone"] = raw.strip()
    return voice


def normalize_glossary(raw: Any) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    items = raw
    if isinstance(raw, dict) and not any(k in raw for k in ("term", "name", "text")):
        items = [{"term": k, "meaning": v} for k, v in raw.items()]
    for item in _as_list(items):
        if isinstance(item, str):
            if ":" in item:
                term, meaning = item.split(":", 1)
            elif "：" in item:
                term, meaning = item.split("：", 1)
            else:
                term, meaning = item, ""
            term, meaning = term.strip(), meaning.strip()
            if term:
                rows.append({"term": term, "meaning": meaning})
            continue
        if not isinstance(item, dict):
            continue
        term = _clean_text(item.get("term") or item.get("name") or item.get("text"))
        if not term:
            continue
        rows.append({"term": term, "meaning": _clean_text(item.get("meaning") or item.get("def") or item.get("definition"))})
    return rows


def normalize_forbidden(raw: Any) -> List[str]:
    extra = _string_items(raw)
    seen = set()
    out: List[str] = []
    for item in DEFAULT_FORBIDDEN + extra:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def normalize_last_block(raw: Any) -> Dict[str, str]:
    if not isinstance(raw, dict):
        return {"heading": "", "excerpt": "", "plan_id": ""}
    return {
        "heading": _clean_text(raw.get("heading") or raw.get("title")),
        "excerpt": _clean_text(raw.get("excerpt") or raw.get("text") or raw.get("sentences")),
        "plan_id": _clean_text(raw.get("plan_id") or raw.get("req")),
    }


def _string_items(raw: Any) -> List[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        return [ln.strip() for ln in raw.replace("\r\n", "\n").split("\n") if ln.strip()]
    out: List[str] = []
    for item in _as_list(raw):
        text = _clean_text(item)
        if text:
            out.append(text)
    return out


def _column(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, str):
        return {"heading": "", "body": raw.strip(), "items": []}
    if not isinstance(raw, dict):
        return {"heading": "", "body": "", "items": []}
    return {
        "heading": _clean_text(raw.get("heading") or raw.get("title")),
        "body": _clean_text(raw.get("body") or raw.get("text")),
        "items": _string_items(raw.get("items") or raw.get("bullets")),
    }


def normalize_block(raw: Any, *, default_id: str = "") -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raise OfficeOutlineError("each Word block must be an object")
    btype = _clean_text(raw.get("type") or raw.get("kind")).lower()
    if btype in {"h1", "h2", "h3"}:
        raw = {**raw, "type": "heading", "level": int(btype[1])}
        btype = "heading"
    if btype in {"p", "body", "text"}:
        btype = "paragraph"
    if btype in {"ul", "bullets", "list"}:
        btype = "bullet_list"
    if btype in {"ol", "ordered", "numbered"}:
        btype = "numbered_list"
    if btype in {"blockquote", "callout"}:
        btype = "quote"
    if btype in {"break", "pagebreak"}:
        btype = "page_break"
    if btype in {"img", "picture"}:
        btype = "image"
    if btype in {"equation", "math", "latex", "formula", "tex"}:
        btype = "equation"
    if btype == "paragraph":
        maybe = extract_standalone_latex(raw.get("text") or raw.get("content") or raw.get("body"))
        if maybe:
            raw = {**raw, "type": "equation", "latex": maybe[0], "display": maybe[1]}
            btype = "equation"
    if btype not in WORD_BLOCK_TYPES:
        raise OfficeOutlineError(
            f"unsupported Word block type `{btype}`. Use: {', '.join(sorted(WORD_BLOCK_TYPES))}"
        )
    bid = _clean_text(raw.get("id")) or default_id or new_item_id("b")
    block: Dict[str, Any] = {"id": bid, "type": btype}
    req = _clean_text(raw.get("req") or raw.get("plan_id") or raw.get("maps_to"))
    if req:
        block["req"] = req
    if btype == "heading":
        try:
            level = int(raw.get("level") or 1)
        except (TypeError, ValueError) as exc:
            raise OfficeOutlineError("heading.level must be 1, 2, or 3") from exc
        if level not in (1, 2, 3):
            raise OfficeOutlineError("heading.level must be 1, 2, or 3")
        text = _clean_text(raw.get("text") or raw.get("title") or raw.get("content"))
        if not text:
            raise OfficeOutlineError("heading.text is required")
        block["level"] = level
        block["text"] = text
    elif btype == "paragraph":
        text = _clean_text(raw.get("text") or raw.get("content") or raw.get("body"))
        if not text:
            raise OfficeOutlineError("paragraph.text is required")
        block["text"] = text
    elif btype in {"bullet_list", "numbered_list"}:
        items = _string_items(raw.get("items") or raw.get("content"))
        if not items:
            raise OfficeOutlineError(f"{btype}.items must be a non-empty array of strings")
        block["items"] = items
    elif btype == "quote":
        text = _clean_text(raw.get("text") or raw.get("content") or raw.get("quote"))
        if not text:
            raise OfficeOutlineError("quote.text is required")
        block["text"] = text
        attr = _clean_text(raw.get("attribution") or raw.get("cite") or raw.get("author"))
        if attr:
            block["attribution"] = attr
    elif btype == "table":
        headers = [str(h).strip() for h in _as_list(raw.get("headers") or raw.get("columns")) if str(h).strip()]
        rows_in = raw.get("rows") or raw.get("data") or []
        rows: List[List[str]] = []
        if not isinstance(rows_in, list):
            raise OfficeOutlineError("table.rows must be an array of arrays")
        for row in rows_in:
            if isinstance(row, dict) and headers:
                rows.append([_clean_text(row.get(h)) for h in headers])
            elif isinstance(row, (list, tuple)):
                rows.append([_clean_text(c) for c in row])
        if not headers and rows:
            headers = [f"列{i}" for i in range(1, len(rows[0]) + 1)]
        if not headers:
            raise OfficeOutlineError("table needs headers or rows")
        block["headers"] = headers
        block["rows"] = rows
    elif btype == "page_break":
        pass
    elif btype == "image":
        path = _clean_text(raw.get("path") or raw.get("file") or raw.get("src"))
        url = _clean_text(raw.get("url"))
        if path.startswith("/api/"):
            url = url or path
            path = ""
        if not path and not url:
            raise OfficeOutlineError("image needs path (workspace) or url (/api/generated-images/…)")
        if path:
            block["path"] = path
        if url:
            block["url"] = url
        caption = _clean_text(raw.get("caption"))
        alt = _clean_text(raw.get("alt") or raw.get("title"))
        if caption:
            block["caption"] = caption
        if alt:
            block["alt"] = alt
        preview = _clean_text(raw.get("preview_url") or raw.get("previewUrl"))
        if preview:
            block["preview_url"] = preview
    elif btype == "equation":
        latex = latex_from_block(raw) or strip_latex_wrappers(raw.get("text") or raw.get("content"))
        if not latex:
            raise OfficeOutlineError("equation.latex is required (LaTeX without wrapping $ $)")
        block["latex"] = latex
        block["display"] = latex_display(raw) if raw.get("display") or raw.get("mode") else (
            extract_standalone_latex(raw.get("text") or "")[1]
            if extract_standalone_latex(raw.get("text") or "")
            else "block"
        )
        caption = _clean_text(raw.get("caption") or raw.get("label"))
        if caption:
            block["caption"] = caption
        # Keep a plain text copy so older preview clients still show something.
        block["text"] = f"$${latex}$$" if block["display"] == "block" else f"${latex}$"
    return block


def normalize_slide(raw: Any, *, default_id: str = "") -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raise OfficeOutlineError("each slide must be an object")
    stype = _clean_text(raw.get("type") or raw.get("kind") or raw.get("layout")).lower()
    aliases = {
        "cover": "title",
        "title_slide": "title",
        "section_header": "section",
        "divider": "section",
        "agenda": "bullets",
        "list": "bullets",
        "columns": "two_column",
        "twocol": "two_column",
        "quote_slide": "quote",
        "picture": "image",
        "image_caption": "image",
        "math": "equation",
        "latex": "equation",
        "formula": "equation",
        "tex": "equation",
    }
    stype = aliases.get(stype, stype)
    if stype not in PPT_SLIDE_TYPES:
        raise OfficeOutlineError(
            f"unsupported slide type `{stype}`. Use: {', '.join(sorted(PPT_SLIDE_TYPES))}"
        )
    sid = _clean_text(raw.get("id")) or default_id or new_item_id("s")
    slide: Dict[str, Any] = {"id": sid, "type": stype}
    req = _clean_text(raw.get("req") or raw.get("plan_id") or raw.get("maps_to"))
    if req:
        slide["req"] = req
    notes = _clean_text(raw.get("notes") or raw.get("speaker_notes") or raw.get("speakerNotes"))
    if notes:
        slide["notes"] = notes
    if stype == "title":
        title = _clean_text(raw.get("title") or raw.get("text"))
        if not title:
            raise OfficeOutlineError("title slide needs title")
        slide["title"] = title
        subtitle = _clean_text(raw.get("subtitle") or raw.get("body"))
        if subtitle:
            slide["subtitle"] = subtitle
    elif stype == "section":
        title = _clean_text(raw.get("title") or raw.get("text"))
        if not title:
            raise OfficeOutlineError("section slide needs title")
        slide["title"] = title
        kicker = _clean_text(raw.get("kicker") or raw.get("label") or raw.get("eyebrow"))
        if kicker:
            slide["kicker"] = kicker
    elif stype == "bullets":
        title = _clean_text(raw.get("title") or raw.get("heading"))
        if not title:
            raise OfficeOutlineError("bullets slide needs title")
        items = _string_items(raw.get("items") or raw.get("bullets"))
        if not items:
            raise OfficeOutlineError("bullets slide needs items[]")
        slide["title"] = title
        slide["items"] = items
    elif stype == "two_column":
        title = _clean_text(raw.get("title") or raw.get("heading"))
        if not title:
            raise OfficeOutlineError("two_column slide needs title")
        slide["title"] = title
        slide["left"] = _column(raw.get("left") or raw.get("col1"))
        slide["right"] = _column(raw.get("right") or raw.get("col2"))
    elif stype == "quote":
        text = _clean_text(raw.get("text") or raw.get("quote") or raw.get("title"))
        if not text:
            raise OfficeOutlineError("quote slide needs text")
        slide["text"] = text
        attr = _clean_text(raw.get("attribution") or raw.get("cite") or raw.get("author"))
        if attr:
            slide["attribution"] = attr
    elif stype == "image":
        path = _clean_text(raw.get("path") or raw.get("file") or raw.get("src"))
        url = _clean_text(raw.get("url"))
        if path.startswith("/api/"):
            url = url or path
            path = ""
        if not path and not url:
            raise OfficeOutlineError("image slide needs path or url")
        if path:
            slide["path"] = path
        if url:
            slide["url"] = url
        title = _clean_text(raw.get("title") or raw.get("heading"))
        caption = _clean_text(raw.get("caption"))
        if title:
            slide["title"] = title
        if caption:
            slide["caption"] = caption
        preview = _clean_text(raw.get("preview_url") or raw.get("previewUrl"))
        if preview:
            slide["preview_url"] = preview
    elif stype == "equation":
        title = _clean_text(raw.get("title") or raw.get("heading"))
        latex = latex_from_block(raw) or strip_latex_wrappers(raw.get("text") or raw.get("content"))
        if not latex:
            raise OfficeOutlineError("equation slide needs latex")
        if title:
            slide["title"] = title
        slide["latex"] = latex
        slide["display"] = "block"
        caption = _clean_text(raw.get("caption") or raw.get("label"))
        if caption:
            slide["caption"] = caption
        slide["text"] = f"$${latex}$$"
    return slide


def _cover_word_blocks(
    title: str,
    subtitle: str,
    author: str,
    plan: Sequence[Dict[str, str]],
    throughline: str = "",
) -> List[Dict[str, Any]]:
    blocks: List[Dict[str, Any]] = [
        {"id": "cover_h1", "type": "heading", "level": 1, "text": title, "req": "cover"},
    ]
    lead = " · ".join(p for p in (subtitle, author) if p)
    if lead:
        blocks.append({"id": "cover_lead", "type": "paragraph", "text": lead, "req": "cover"})
    if throughline:
        blocks.append(
            {
                "id": "cover_throughline",
                "type": "quote",
                "text": throughline,
                "attribution": "主线",
                "req": "cover",
            }
        )
    blocks.append({"id": "cover_struct", "type": "heading", "level": 2, "text": "文档结构", "req": "cover"})
    if plan:
        blocks.append(
            {
                "id": "cover_plan",
                "type": "numbered_list",
                "items": [f"{row['title']}" + (f"  — {row['maps_to']}" if row.get("maps_to") and row["maps_to"] != row["title"] else "") for row in plan],
                "req": "cover",
            }
        )
    else:
        blocks.append(
            {
                "id": "cover_plan",
                "type": "paragraph",
                "text": "（尚未规划章节；请用 office_append 按节写入。）",
                "req": "cover",
            }
        )
    return blocks


def _cover_ppt_slides(
    title: str,
    subtitle: str,
    plan: Sequence[Dict[str, str]],
    throughline: str = "",
) -> List[Dict[str, Any]]:
    slides: List[Dict[str, Any]] = [
        {
            "id": "cover_title",
            "type": "title",
            "title": title,
            "subtitle": subtitle or throughline or "Nexus Lark Mind",
            "req": "cover",
        }
    ]
    if plan:
        notes = "先对照用户要求过一遍结构，再逐页展开。"
        if throughline:
            notes = f"主线：{throughline} " + notes
        slides.append(
            {
                "id": "cover_agenda",
                "type": "bullets",
                "title": "议程",
                "items": [row["title"] for row in plan],
                "notes": notes,
                "req": "cover",
            }
        )
    return slides


def empty_outline(
    *,
    kind: str,
    title: str,
    subtitle: str = "",
    author: str = "",
    plan: Optional[Any] = None,
    requirements: Optional[Any] = None,
    theme: Optional[Any] = None,
    style_id: str = "",
    doc_id: str = "",
    file_name: str = "",
    throughline: str = "",
    thesis: str = "",
    glossary: Optional[Any] = None,
    terms: Optional[Any] = None,
    voice: Optional[Any] = None,
    forbidden: Optional[Any] = None,
) -> Dict[str, Any]:
    kind_n = normalize_kind(kind)
    title_n = _clean_text(title) or ("未命名文稿" if kind_n == "docx" else "未命名演示")
    throughline_n = normalize_throughline(throughline or thesis, title=title_n, required=True)
    plan_n = normalize_plan(plan)
    reqs = normalize_requirements(requirements)
    if not plan_n and reqs:
        plan_n = [
            {"id": r["id"], "title": r["text"][:40], "maps_to": r["text"], "status": "pending"} for r in reqs
        ]
    if not plan_n:
        raise OfficeOutlineError(
            "office_create requires a plan[] of section/slide titles that map the user's request. "
            "Do not skip the outline."
        )
    del theme  # packs own colors; office_create must not set theme
    sid = normalize_style_id(style_id or DEFAULT_STYLE_ID)
    # Auto-link requirements to plan items when missing.
    if reqs and plan_n:
        for req in reqs:
            if req.get("mapped_to"):
                continue
            for row in plan_n:
                if req["text"] in row["title"] or row["title"] in req["text"] or row["id"] == req["id"]:
                    req["mapped_to"] = row["id"]
                    break
            if not req.get("mapped_to"):
                req["mapped_to"] = plan_n[min(len(plan_n) - 1, max(0, reqs.index(req)))]["id"]
    outline: Dict[str, Any] = {
        "schema": SCHEMA,
        "doc_id": doc_id or new_doc_id(),
        "kind": kind_n,
        "title": title_n,
        "subtitle": _clean_text(subtitle),
        "author": _clean_text(author),
        "style_id": sid,
        "theme": normalize_theme(style_id=sid),
        "throughline": throughline_n,
        "voice": normalize_voice(voice),
        "glossary": normalize_glossary(glossary if glossary is not None else terms),
        "forbidden": normalize_forbidden(forbidden),
        "last_block": {"heading": title_n, "excerpt": throughline_n, "plan_id": ""},
        "plan": plan_n,
        "requirements": reqs,
        "blocks": _cover_word_blocks(
            title_n, _clean_text(subtitle), _clean_text(author), plan_n, throughline_n
        )
        if kind_n == "docx"
        else [],
        "slides": _cover_ppt_slides(title_n, _clean_text(subtitle), plan_n, throughline_n)
        if kind_n == "pptx"
        else [],
        "status": "writing",
        "writing": False,
        "last_op": "create",
        "last_ids": ["cover_h1", "cover_plan"] if kind_n == "docx" else ["cover_title", "cover_agenda"][: 1 + int(bool(plan_n))],
        "file_name": _clean_text(file_name),
        "path": "",
        "download_url": "",
    }
    return outline


def parse_outline(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, str):
        import json

        raw = json.loads(raw)
    if not isinstance(raw, dict):
        raise OfficeOutlineError("outline must be a JSON object")
    kind = normalize_kind(raw.get("kind") or ("pptx" if raw.get("slides") else "docx"))
    sid = normalize_style_id(raw.get("style_id"))
    theme = normalize_theme(style_id=sid)
    blocks = [normalize_block(b) for b in _as_list(raw.get("blocks"))]
    slides = [normalize_slide(s) for s in _as_list(raw.get("slides"))]
    return {
        "schema": SCHEMA,
        "doc_id": _clean_text(raw.get("doc_id")) or new_doc_id(),
        "kind": kind,
        "title": _clean_text(raw.get("title")) or "Untitled",
        "subtitle": _clean_text(raw.get("subtitle")),
        "author": _clean_text(raw.get("author")),
        "style_id": sid,
        "theme": theme,
        "throughline": normalize_throughline(
            raw.get("throughline") or raw.get("thesis"), title=_clean_text(raw.get("title")), required=False
        ),
        "voice": normalize_voice(raw.get("voice")),
        "glossary": normalize_glossary(raw.get("glossary") if raw.get("glossary") is not None else raw.get("terms")),
        "forbidden": normalize_forbidden(raw.get("forbidden")),
        "last_block": normalize_last_block(raw.get("last_block") or raw.get("lastBlock")),
        "plan": normalize_plan(raw.get("plan")),
        "requirements": normalize_requirements(raw.get("requirements")),
        "blocks": blocks,
        "slides": slides,
        "status": _clean_text(raw.get("status")) or "writing",
        "writing": bool(raw.get("writing")),
        "last_op": _clean_text(raw.get("last_op")),
        "last_ids": [str(x) for x in _as_list(raw.get("last_ids")) if str(x).strip()],
        "file_name": _clean_text(raw.get("file_name")),
        "path": _clean_text(raw.get("path")),
        "download_url": _clean_text(raw.get("download_url") or raw.get("downloadUrl")),
    }


def _existing_ids(outline: Dict[str, Any]) -> set:
    ids = set()
    for item in list(outline.get("blocks") or []) + list(outline.get("slides") or []):
        if isinstance(item, dict) and item.get("id"):
            ids.add(str(item["id"]))
    return ids


def _plan_index(outline: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    return {str(row.get("id") or ""): row for row in (outline.get("plan") or []) if isinstance(row, dict) and row.get("id")}


def _infer_plan_id(payload: Dict[str, Any], items: Sequence[Any]) -> str:
    named = _clean_text(payload.get("plan_id") or payload.get("req") or payload.get("planId"))
    if named:
        return named
    reqs = []
    for raw in items:
        if isinstance(raw, dict):
            rid = _clean_text(raw.get("req") or raw.get("plan_id") or raw.get("maps_to"))
            if rid and rid != "cover":
                reqs.append(rid)
    if reqs and all(r == reqs[0] for r in reqs):
        return reqs[0]
    return ""


def _looks_like_conclusion(title: str) -> bool:
    t = _clean_text(title).lower()
    return t in CONCLUSION_TITLES or any(t == c or t.startswith(c) for c in CONCLUSION_TITLES)


def _title_match(a: str, b: str) -> bool:
    left, right = _clean_text(a), _clean_text(b)
    if not left or not right:
        return False
    return left == right or left in right or right in left


def _sentences(text: str, n: int = 2) -> str:
    parts = [p.strip() for p in re.split(r"(?<=[。！？.!?])\s*", str(text or "").strip()) if p.strip()]
    return "".join(parts[-n:]) if parts else str(text or "").strip()


def _refresh_cover_structure(outline: Dict[str, Any]) -> None:
    plan = [row for row in (outline.get("plan") or []) if isinstance(row, dict)]
    items = [
        f"{row['title']}"
        + (f"  — {row['maps_to']}" if row.get("maps_to") and row["maps_to"] != row["title"] else "")
        for row in plan
        if row.get("title")
    ]
    if outline.get("kind") == "docx":
        for block in outline.get("blocks") or []:
            if not isinstance(block, dict):
                continue
            if block.get("id") == "cover_plan":
                if items:
                    block["type"] = "numbered_list"
                    block["items"] = items
                    block.pop("text", None)
                else:
                    block["type"] = "paragraph"
                    block["text"] = "（尚未规划章节；请用 office_append 按节写入。）"
                    block.pop("items", None)
            if block.get("id") == "cover_throughline" and outline.get("throughline"):
                block["text"] = str(outline.get("throughline") or "")
    else:
        for slide in outline.get("slides") or []:
            if isinstance(slide, dict) and slide.get("id") == "cover_agenda":
                slide["items"] = [row.get("title") or "" for row in plan if row.get("title")]
                through = _clean_text(outline.get("throughline"))
                if through:
                    slide["notes"] = f"主线：{through} 先对照用户要求过一遍结构，再逐页展开。"


def _mark_plan_status(outline: Dict[str, Any], plan_id: str, status: str) -> None:
    for row in outline.get("plan") or []:
        if isinstance(row, dict) and row.get("id") == plan_id:
            row["status"] = status


def _update_last_block(outline: Dict[str, Any], appended: Sequence[Dict[str, Any]], plan_id: str) -> None:
    heading = ""
    prose: List[str] = []
    for item in appended:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "heading":
            heading = str(item.get("text") or heading)
            continue
        if item.get("type") == "equation":
            continue
        if item.get("type") in {"paragraph", "quote"}:
            prose.append(str(item.get("text") or ""))
        elif item.get("items"):
            prose.extend(str(x) for x in item.get("items") or [] if not str(x).startswith("$"))
        if item.get("title"):
            heading = heading or str(item.get("title") or "")
            if item.get("text") and item.get("type") not in {"title", "equation"}:
                prose.append(str(item.get("text") or ""))
    if not heading:
        for item in reversed(list(outline.get("blocks") or []) + list(outline.get("slides") or [])):
            if not isinstance(item, dict):
                continue
            if item.get("type") == "heading":
                heading = str(item.get("text") or "")
                break
            if item.get("title"):
                heading = str(item.get("title") or "")
                break
    excerpt = _sentences(" ".join(t for t in prose if t), 2)
    outline["last_block"] = {"heading": heading, "excerpt": excerpt, "plan_id": plan_id}


def _validate_append_contract(
    outline: Dict[str, Any],
    payload: Dict[str, Any],
    items: Sequence[Any],
    *,
    kind: str,
) -> str:
    plan_map = _plan_index(outline)
    plan_id = _infer_plan_id(payload, items)
    if not plan_id:
        raise OfficeOutlineError(
            "office_append requires plan_id (the plan[] row being filled). "
            "Do not invent a section — call office_revise_plan first if the user added one."
        )
    if plan_id != "cover" and plan_id not in plan_map:
        raise OfficeOutlineError(
            f"unknown plan_id `{plan_id}`. Use an existing plan[] id or call office_revise_plan to add the section."
        )
    row = plan_map.get(plan_id) or {}
    if plan_id != "cover" and _looks_like_conclusion(str(row.get("title") or "")):
        earlier = []
        for p in outline.get("plan") or []:
            if not isinstance(p, dict):
                continue
            if p.get("id") == plan_id:
                break
            if p.get("status") != "done":
                earlier.append(p)
        if earlier:
            titles = ", ".join(str(p.get("title") or p.get("id")) for p in earlier)
            raise OfficeOutlineError(
                f"forbidden: do not jump to the conclusion (`{row.get('title')}`) while earlier plan rows "
                f"are still pending ({titles})."
            )

    headings: List[Tuple[int, str]] = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        if kind == "docx" and str(raw.get("type") or "") in {"heading", "h1", "h2", "h3"}:
            try:
                level = int(raw.get("level") or (str(raw.get("type") or "h2")[-1] if str(raw.get("type")).startswith("h") else 2))
            except (TypeError, ValueError):
                level = 2
            headings.append((level, _clean_text(raw.get("text") or raw.get("title"))))
        if kind == "pptx" and str(raw.get("type") or "") in {"title", "section", "bullets", "two_column", "equation"}:
            headings.append((1, _clean_text(raw.get("title") or raw.get("text"))))

    plan_titles = [str(p.get("title") or "") for p in (outline.get("plan") or []) if isinstance(p, dict)]
    current_title = str(row.get("title") or "")
    for level, title in headings:
        if not title or title in COVER_HEADINGS:
            continue
        if kind == "docx" and level >= 3:
            continue
        if _title_match(title, current_title) or any(_title_match(title, t) for t in plan_titles):
            other = next((p for p in (outline.get("plan") or []) if isinstance(p, dict) and _title_match(title, str(p.get("title") or ""))), None)
            if other and other.get("id") not in {plan_id, ""} and not _title_match(title, current_title):
                raise OfficeOutlineError(
                    f"heading `{title}` belongs to plan `{other.get('id')}` ({other.get('title')}), "
                    f"not `{plan_id}`. Fill one plan row per office_append."
                )
            continue
        if level <= 2:
            raise OfficeOutlineError(
                f"heading `{title}` is not on the document plan. Call office_revise_plan to add it first."
            )
    return plan_id


def apply_append(outline: Dict[str, Any], payload: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    kind = outline.get("kind") or "docx"
    blocks_in = payload.get("blocks")
    slides_in = payload.get("slides")
    if blocks_in is None and payload.get("block"):
        blocks_in = [payload.get("block")]
    if slides_in is None and payload.get("slide"):
        slides_in = [payload.get("slide")]
    blocks_in = _as_list(blocks_in)
    slides_in = _as_list(slides_in)
    if kind == "docx":
        if slides_in:
            raise OfficeOutlineError("this document is Word (.docx); append blocks[], not slides[]")
        if not blocks_in:
            raise OfficeOutlineError("office_append requires blocks[] (one heading + its body, not the whole doc)")
        if len(blocks_in) > MAX_APPEND_BLOCKS:
            raise OfficeOutlineError(
                f"append at most {MAX_APPEND_BLOCKS} Word blocks per call — write one section at a time"
            )
        incoming = blocks_in
    else:
        if blocks_in and not slides_in:
            raise OfficeOutlineError("this document is PowerPoint (.pptx); append slides[], not Word blocks[]")
        if not slides_in:
            raise OfficeOutlineError("office_append requires slides[] (preferably one slide)")
        if len(slides_in) > MAX_APPEND_SLIDES:
            raise OfficeOutlineError(
                f"append at most {MAX_APPEND_SLIDES} slides per call — one slide at a time is best"
            )
        incoming = slides_in

    plan_id = _validate_append_contract(outline, payload, incoming, kind=str(kind))
    bridge = _clean_text(payload.get("bridge") or payload.get("transition"))

    used = _existing_ids(outline)
    appended: List[str] = []
    written: List[Dict[str, Any]] = []
    if kind == "docx":
        dest = list(outline.get("blocks") or [])
        if bridge:
            bid = new_item_id("b")
            while bid in used:
                bid = new_item_id("b")
            block = normalize_block({"type": "paragraph", "text": bridge, "req": plan_id}, default_id=bid)
            used.add(block["id"])
            dest.append(block)
            appended.append(block["id"])
            written.append(block)
        for raw in blocks_in:
            if isinstance(raw, dict) and not raw.get("req"):
                raw = {**raw, "req": plan_id}
            bid = _clean_text(raw.get("id") if isinstance(raw, dict) else "") or new_item_id("b")
            while bid in used:
                bid = new_item_id("b")
            block = normalize_block(raw, default_id=bid)
            if plan_id and not block.get("req"):
                block["req"] = plan_id
            used.add(block["id"])
            dest.append(block)
            appended.append(block["id"])
            written.append(block)
        outline["blocks"] = dest
    else:
        dest = list(outline.get("slides") or [])
        for raw in slides_in:
            if isinstance(raw, dict) and not raw.get("req"):
                raw = {**raw, "req": plan_id}
            if bridge and isinstance(raw, dict):
                raw = dict(raw)
                if raw.get("type") in {"bullets", "agenda", "list"}:
                    items = list(raw.get("items") or raw.get("bullets") or [])
                    if bridge not in items:
                        raw["items"] = [bridge, *items]
                notes = _clean_text(raw.get("notes"))
                if bridge not in notes:
                    raw["notes"] = f"衔接：{bridge}" + (f"\n{notes}" if notes else "")
            sid = _clean_text(raw.get("id") if isinstance(raw, dict) else "") or new_item_id("s")
            while sid in used:
                sid = new_item_id("s")
            slide = normalize_slide(raw, default_id=sid)
            if plan_id and not slide.get("req"):
                slide["req"] = plan_id
            used.add(slide["id"])
            dest.append(slide)
            appended.append(slide["id"])
            written.append(slide)
        outline["slides"] = dest

    if plan_id and plan_id != "cover":
        _mark_plan_status(outline, plan_id, "done")
    _update_last_block(outline, written, plan_id)
    outline["last_op"] = "append"
    outline["last_ids"] = appended
    outline["status"] = "writing"
    outline["writing"] = False
    return outline, appended


def apply_revise_plan(outline: Dict[str, Any], payload: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """Add / retitle plan rows and refresh the cover structure. Does not write body."""
    if payload.get("blocks") or payload.get("slides") or payload.get("block") or payload.get("slide"):
        raise OfficeOutlineError("office_revise_plan only updates the contract (plan/throughline/glossary), not body")
    through = _clean_text(payload.get("throughline") or payload.get("thesis"))
    if through:
        outline["throughline"] = through
    if payload.get("voice") is not None:
        outline["voice"] = normalize_voice(payload.get("voice"))
    if payload.get("glossary") is not None or payload.get("terms") is not None:
        incoming = normalize_glossary(payload.get("glossary") if payload.get("glossary") is not None else payload.get("terms"))
        existing = {row["term"]: row for row in (outline.get("glossary") or []) if isinstance(row, dict)}
        for row in incoming:
            existing[row["term"]] = row
        outline["glossary"] = list(existing.values())
    if payload.get("forbidden") is not None:
        outline["forbidden"] = normalize_forbidden(payload.get("forbidden"))
    if payload.get("requirements") is not None:
        extra = normalize_requirements(payload.get("requirements"))
        have = {str(r.get("id") or ""): r for r in (outline.get("requirements") or []) if isinstance(r, dict)}
        for row in extra:
            have[row["id"]] = row
        outline["requirements"] = list(have.values())

    plan = list(outline.get("plan") or [])
    used_ids = {str(r.get("id") or "") for r in plan if isinstance(r, dict)}
    added_ids: List[str] = []
    for raw in _as_list(payload.get("add") or payload.get("plan_add") or payload.get("sections")):
        if isinstance(raw, str):
            raw = {"title": raw}
        if not isinstance(raw, dict):
            continue
        title = _clean_text(raw.get("title") or raw.get("text") or raw.get("heading"))
        if not title:
            continue
        rid = _clean_text(raw.get("id")) or f"p{len(plan) + 1}"
        while rid in used_ids:
            rid = new_item_id("p")
        row = {
            "id": rid,
            "title": title,
            "maps_to": _clean_text(raw.get("maps_to") or raw.get("requirement")) or title,
            "status": "pending",
        }
        after = _clean_text(raw.get("after"))
        insert_at = len(plan)
        if after:
            for i, existing in enumerate(plan):
                if isinstance(existing, dict) and existing.get("id") == after:
                    insert_at = i + 1
                    break
        plan.insert(insert_at, row)
        used_ids.add(rid)
        added_ids.append(rid)

    if not plan:
        raise OfficeOutlineError("plan[] cannot be empty — add at least one section")
    outline["plan"] = plan
    _refresh_cover_structure(outline)
    outline["last_op"] = "revise_plan"
    outline["last_ids"] = ["cover_plan"] if outline.get("kind") == "docx" else ["cover_agenda"]
    outline["status"] = "writing"
    outline["writing"] = False
    return outline, added_ids


def apply_replace(outline: Dict[str, Any], payload: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    target_id = _clean_text(payload.get("id") or payload.get("block_id") or payload.get("slide_id"))
    raw = payload.get("block") or payload.get("slide") or payload.get("item")
    if not target_id:
        raise OfficeOutlineError("office_replace requires id of the block/slide to replace")
    if not isinstance(raw, dict):
        raise OfficeOutlineError("office_replace requires block{} or slide{}")
    kind = outline.get("kind") or "docx"
    key = "blocks" if kind == "docx" else "slides"
    items = list(outline.get(key) or [])
    found = False
    for i, item in enumerate(items):
        if str(item.get("id")) == target_id:
            nxt = normalize_block(raw, default_id=target_id) if kind == "docx" else normalize_slide(raw, default_id=target_id)
            nxt["id"] = target_id
            items[i] = nxt
            found = True
            break
    if not found:
        raise OfficeOutlineError(f"no block/slide with id `{target_id}`")
    outline[key] = items
    outline["last_op"] = "replace"
    outline["last_ids"] = [target_id]
    outline["status"] = "writing"
    outline["writing"] = False
    return outline, [target_id]


def alignment_report(outline: Dict[str, Any]) -> Dict[str, Any]:
    """Map user requirements / plan rows to written headings or slides."""
    plan = list(outline.get("plan") or [])
    reqs = list(outline.get("requirements") or [])
    blocks = [b for b in (outline.get("blocks") or []) if isinstance(b, dict)]
    slides = [s for s in (outline.get("slides") or []) if isinstance(s, dict)]
    written_reqs = {str(x.get("req") or "") for x in blocks + slides if x.get("req")}
    titles: List[str] = []
    for b in blocks:
        if b.get("type") == "heading":
            titles.append(str(b.get("text") or ""))
    for s in slides:
        titles.append(str(s.get("title") or s.get("text") or ""))

    def _covered(row: Dict[str, str]) -> bool:
        if str(row.get("status") or "") == "done":
            return True
        rid = str(row.get("id") or "")
        title = str(row.get("title") or row.get("text") or "")
        if rid and rid in written_reqs:
            return True
        if title and any(title in t or t in title for t in titles if t):
            return True
        return False

    plan_out = []
    for row in plan:
        plan_out.append({**row, "filled": _covered(row)})
    req_out = []
    for row in reqs:
        mapped = str(row.get("mapped_to") or "")
        filled = (mapped in written_reqs) or _covered(row)
        req_out.append({**row, "filled": filled})
    return {
        "plan": plan_out,
        "requirements": req_out,
        "filled_plan": sum(1 for r in plan_out if r.get("filled")),
        "total_plan": len(plan_out),
        "filled_requirements": sum(1 for r in req_out if r.get("filled")),
        "total_requirements": len(req_out),
    }


def compact_outline(outline: Dict[str, Any]) -> Dict[str, Any]:
    """Small payload for the model (not the Canvas body)."""
    align = alignment_report(outline)
    blocks = []
    for b in outline.get("blocks") or []:
        if not isinstance(b, dict):
            continue
        row = {"id": b.get("id"), "type": b.get("type")}
        if b.get("text"):
            row["text"] = str(b["text"])[:80]
        if b.get("level"):
            row["level"] = b["level"]
        if b.get("req"):
            row["req"] = b["req"]
        if b.get("type") == "equation" and b.get("latex"):
            row["latex"] = str(b["latex"])[:80]
        blocks.append(row)
    slides = []
    for s in outline.get("slides") or []:
        if not isinstance(s, dict):
            continue
        row = {"id": s.get("id"), "type": s.get("type"), "title": (s.get("title") or s.get("text") or "")[:80]}
        if s.get("req"):
            row["req"] = s["req"]
        if s.get("type") == "equation" and s.get("latex"):
            row["latex"] = str(s["latex"])[:80]
        slides.append(row)
    return {
        "doc_id": outline.get("doc_id"),
        "kind": outline.get("kind"),
        "title": outline.get("title"),
        "throughline": outline.get("throughline") or "",
        "voice": outline.get("voice") or {},
        "glossary": outline.get("glossary") or [],
        "forbidden": outline.get("forbidden") or [],
        "last_block": outline.get("last_block") or {},
        "plan": outline.get("plan") or [],
        "requirements": outline.get("requirements") or [],
        "alignment": align,
        "blocks": blocks,
        "slides": slides,
        "last_op": outline.get("last_op"),
        "last_ids": outline.get("last_ids") or [],
        "status": outline.get("status"),
        "path": outline.get("path") or "",
        "download_url": outline.get("download_url") or "",
        "counts": {"blocks": len(blocks), "slides": len(slides)},
    }


def next_hint(outline: Dict[str, Any]) -> str:
    align = alignment_report(outline)
    last = outline.get("last_block") or {}
    terms = [str(g.get("term") or "") for g in (outline.get("glossary") or []) if isinstance(g, dict) and g.get("term")]
    term_bit = f" Keep glossary terms: {', '.join(terms[:8])}." if terms else ""
    through = _clean_text(outline.get("throughline"))
    through_bit = f" Throughline: {through}." if through else ""
    last_bit = ""
    if last.get("excerpt") or last.get("heading"):
        last_bit = (
            f" Bridge from last_block「{last.get('heading') or ''}：{_clean_text(last.get('excerpt'))[:80]}」."
        )
    for row in align["plan"]:
        if not row.get("filled"):
            kind = outline.get("kind")
            if kind == "pptx":
                return (
                    f"Next: office_append plan_id=`{row['id']}` one slide ({row['title']}). "
                    "Set req to that plan id. Prefer type bullets|section|two_column|quote|image|equation."
                    f"{last_bit}{term_bit}{through_bit}"
                )
            return (
                f"Next: office_append plan_id=`{row['id']}` ({row['title']}) — "
                "heading + body/list/quote/table/equation as needed. Optional bridge sentence. "
                f"Do not dump the rest.{last_bit}{term_bit}{through_bit}"
            )
    return (
        "All planned sections are present. Call office_save if the file should be finalized, "
        "office_replace to revise a block by id, or office_revise_plan if the user added a section."
    )


def iter_image_refs(outline: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    for item in list(outline.get("blocks") or []) + list(outline.get("slides") or []):
        if isinstance(item, dict) and item.get("type") == "image":
            yield item
