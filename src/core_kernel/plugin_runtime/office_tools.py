"""Builtin Office tools — incremental Word/PPT via a shared JSON outline."""

from __future__ import annotations

from typing import Any, Dict, List

from src.common.errors import PluginError, ValidationAppError
from src.core_kernel.plugin_runtime.invoke_context import get_workspace_cwd, get_workspace_meta
from src.core_kernel.plugin_runtime.lifecycle import BasePlugin, PluginManifest
from src.core_kernel.plugin_runtime.office_outline import (
    OfficeOutlineError,
    apply_append,
    apply_replace,
    apply_revise_plan,
    compact_outline,
    empty_outline,
    next_hint,
)
from src.core_kernel.plugin_runtime.office_style import apply_style_to_outline
from src.core_kernel.plugin_runtime.office_store import (
    download_url,
    get_outline,
    persist_workspace_copy,
    put_outline,
    suggested_file_name,
    write_binary,
)
from src.core_kernel.plugin_runtime.office_writer import render_outline, resolve_image_file

_PLAN_ITEM = {
    "type": "object",
    "properties": {
        "id": {"type": "string", "description": "Stable plan id, e.g. p1"},
        "title": {"type": "string", "description": "Section or slide title matching the user ask"},
        "maps_to": {"type": "string", "description": "Which user requirement this row covers"},
        "status": {"type": "string", "enum": ["pending", "done", "writing"], "description": "Filled by the backend"},
    },
    "required": ["title"],
}

_GLOSSARY_ITEM = {
    "type": "object",
    "properties": {
        "term": {"type": "string"},
        "meaning": {"type": "string"},
    },
    "required": ["term"],
}

_VOICE = {
    "type": "object",
    "properties": {
        "tone": {"type": "string", "description": "语气，如 专业、克制、书面"},
        "person": {"type": "string", "description": "人称，如 第三人称"},
        "tense": {"type": "string", "description": "时态"},
    },
}

_REQ_ITEM = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "text": {"type": "string", "description": "Restated user requirement"},
        "mapped_to": {"type": "string", "description": "plan id this requirement maps to"},
    },
    "required": ["text"],
}

_WORD_BLOCK = {
    "type": "object",
    "description": (
        "One Word block. type=heading|paragraph|bullet_list|numbered_list|quote|table|page_break|image|equation. "
        "heading needs level 1-3 + text. lists need items[]. table needs headers[] + rows[][]. "
        "equation needs latex (no wrapping $$ required) + optional display=inline|block. "
        "You may also put $...$ / $$...$$ inside paragraph/list text. "
        "image needs path (workspace) or url (/api/generated-images/…). Set req to the plan id."
    ),
    "properties": {
        "id": {"type": "string"},
        "type": {
            "type": "string",
            "enum": [
                "heading",
                "paragraph",
                "bullet_list",
                "numbered_list",
                "quote",
                "table",
                "page_break",
                "image",
                "equation",
            ],
        },
        "level": {"type": "integer", "description": "heading level 1-3"},
        "text": {"type": "string"},
        "latex": {"type": "string", "description": "LaTeX for type=equation (also accepted as $...$ in text)"},
        "display": {"type": "string", "enum": ["inline", "block"], "description": "equation layout"},
        "items": {"type": "array", "items": {"type": "string"}},
        "headers": {"type": "array", "items": {"type": "string"}},
        "rows": {"type": "array", "items": {"type": "array", "items": {"type": "string"}}},
        "attribution": {"type": "string"},
        "path": {"type": "string"},
        "url": {"type": "string"},
        "caption": {"type": "string"},
        "alt": {"type": "string"},
        "req": {"type": "string", "description": "plan/requirement id this block fulfills"},
    },
    "required": ["type"],
}

_PPT_SLIDE = {
    "type": "object",
    "description": (
        "One slide. type=title|section|bullets|two_column|quote|image|equation. "
        "bullets needs title+items[]; two_column needs title+left{heading,items,body}+right{}; "
        "equation needs latex + optional title/caption. $...$ in items is OK. "
        "image needs path or url + optional caption; notes=speaker notes. Set req to the plan id."
    ),
    "properties": {
        "id": {"type": "string"},
        "type": {
            "type": "string",
            "enum": ["title", "section", "bullets", "two_column", "quote", "image", "equation"],
        },
        "latex": {"type": "string", "description": "LaTeX for type=equation"},
        "title": {"type": "string"},
        "subtitle": {"type": "string"},
        "kicker": {"type": "string"},
        "text": {"type": "string"},
        "items": {"type": "array", "items": {"type": "string"}},
        "left": {"type": "object"},
        "right": {"type": "object"},
        "attribution": {"type": "string"},
        "path": {"type": "string"},
        "url": {"type": "string"},
        "caption": {"type": "string"},
        "notes": {"type": "string", "description": "Speaker notes"},
        "req": {"type": "string"},
    },
    "required": ["type"],
}

TOOLS: List[Dict[str, Any]] = [
    {
        "name": "office_create",
        "description": (
            "Start a Word (.docx) or PowerPoint (.pptx) document. JSON outline is the source of truth. "
            "REQUIRED: throughline (一句话系统观 / thesis) + full plan[] of section/slide titles. "
            "Also pass requirements[] mapping each user ask to a plan id, plus glossary/terms and voice when names/tone matter. "
            "This call ONLY writes the document contract + cover / TOC / agenda — never the full body. "
            "Do NOT dump a giant blob. Next calls MUST be office_append (one section or one slide). "
            "If the user later asks for a new section, call office_revise_plan first. "
            "Stay style-blind: do not pass theme/colors/fonts, and do not write 商业风/学术风/配色/花哨排版 into the text. "
            "Visual style is applied by the product after you write. "
            "Canvas opens automatically with a live preview. Engine: python-docx / python-pptx."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "kind": {
                    "type": "string",
                    "enum": ["docx", "pptx"],
                    "description": "docx = Word, pptx = PowerPoint",
                },
                "title": {"type": "string", "description": "Document / deck title"},
                "subtitle": {"type": "string"},
                "author": {"type": "string"},
                "file_name": {"type": "string", "description": "Optional workspace file name (.docx/.pptx)"},
                "throughline": {
                    "type": "string",
                    "description": "One-sentence 系统观 / thesis the whole document must serve. Required.",
                },
                "thesis": {"type": "string", "description": "Alias of throughline"},
                "plan": {
                    "type": "array",
                    "description": "Ordered section/slide titles matching the user request. Required.",
                    "items": _PLAN_ITEM,
                },
                "requirements": {
                    "type": "array",
                    "description": "Each user requirement restated and mapped to a plan id.",
                    "items": _REQ_ITEM,
                },
                "glossary": {
                    "type": "array",
                    "description": "Names that must stay consistent across appends.",
                    "items": _GLOSSARY_ITEM,
                },
                "terms": {
                    "type": "array",
                    "description": "Alias of glossary",
                    "items": _GLOSSARY_ITEM,
                },
                "voice": _VOICE,
                "forbidden": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Extra constraints (defaults already ban restating the intro and early conclusions)",
                },
            },
            "required": ["kind", "title", "plan", "throughline"],
        },
    },
    {
        "name": "office_append",
        "description": (
            "Incrementally write the next slice of the document created by office_create. "
            "MUST name plan_id (the plan[] row being filled). "
            "Optional bridge: one sentence that connects from last_block (衔接). "
            "Word: 1 heading plus its local blocks (paragraph / list / quote / table / image / equation / page_break). "
            "Max 8 blocks. PowerPoint: preferably ONE slide (max 3). "
            "Do not introduce a section that is not on the plan — call office_revise_plan first. "
            "Keep glossary terms and the throughline. Do not restate the intro or jump to the conclusion early. "
            "Write semantic content only — no colors, fonts, or 花哨 visual styling in the text. "
            "Never send the entire remaining document. Never use write_file for .docx/.pptx. "
            "Canvas updates live, one block/slide at a time."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "doc_id": {"type": "string", "description": "Id returned by office_create"},
                "plan_id": {
                    "type": "string",
                    "description": "plan[] id this append fills. Required (or set req on every block).",
                },
                "bridge": {
                    "type": "string",
                    "description": "Optional 衔接 sentence that continues from last_block",
                },
                "blocks": {
                    "type": "array",
                    "description": "Word blocks to append (one section)",
                    "items": _WORD_BLOCK,
                },
                "slides": {
                    "type": "array",
                    "description": "PPT slides to append (one slide preferred)",
                    "items": _PPT_SLIDE,
                },
            },
            "required": ["doc_id"],
        },
    },
    {
        "name": "office_revise_plan",
        "description": (
            "Update the document contract without writing body. "
            "Use when the user just asked for a new section/slide that is not on plan[]. "
            "Pass add[{id,title,maps_to,after}] — after is the preceding plan id. "
            "May also refresh throughline / glossary / voice / forbidden / requirements. "
            "Then office_append the new plan_id."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "doc_id": {"type": "string"},
                "add": {
                    "type": "array",
                    "description": "New plan rows to insert",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "title": {"type": "string"},
                            "maps_to": {"type": "string"},
                            "after": {"type": "string", "description": "Insert after this plan id"},
                        },
                        "required": ["title"],
                    },
                },
                "throughline": {"type": "string"},
                "glossary": {"type": "array", "items": _GLOSSARY_ITEM},
                "voice": _VOICE,
                "forbidden": {"type": "array", "items": {"type": "string"}},
                "requirements": {"type": "array", "items": _REQ_ITEM},
            },
            "required": ["doc_id"],
        },
    },
    {
        "name": "office_replace",
        "description": (
            "Replace a single existing block or slide by id. Use this to revise, not to dump a new document. "
            "id must already exist (from create/append)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "doc_id": {"type": "string"},
                "id": {"type": "string", "description": "block id or slide id"},
                "block": _WORD_BLOCK,
                "slide": _PPT_SLIDE,
            },
            "required": ["doc_id", "id"],
        },
    },
    {
        "name": "office_save",
        "description": (
            "Rebuild the .docx/.pptx from the current JSON outline and persist it "
            "(workspace `.nlm/office/` when local cwd is bound, plus a downloadable copy). "
            "Call after the planned sections are written. Mention the returned path in your reply."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "doc_id": {"type": "string"},
                "file_name": {"type": "string"},
            },
            "required": ["doc_id"],
        },
    },
]


def _cwd_and_kind() -> tuple[str, str]:
    cwd = (get_workspace_cwd() or "").strip()
    meta = get_workspace_meta()
    kind = str(meta.get("workspace_kind") or meta.get("kind") or "local").strip() or "local"
    return cwd, kind


def _hydrate_images(outline: Dict[str, Any], cwd: str) -> None:
    doc_id = str(outline.get("doc_id") or "")
    from src.core_kernel.plugin_runtime.office_outline import iter_image_refs

    for item in iter_image_refs(outline):
        resolve_image_file(item, cwd=cwd, doc_id=doc_id)


def _materialize(outline: Dict[str, Any]) -> Dict[str, Any]:
    cwd, ws_kind = _cwd_and_kind()
    _hydrate_images(outline, cwd)
    data = render_outline(outline, cwd=cwd)
    doc_id = str(outline["doc_id"])
    dest = write_binary(doc_id, str(outline.get("kind") or "docx"), data)
    outline["download_url"] = download_url(doc_id)
    file_name = suggested_file_name(outline)
    ws: Dict[str, Any] = {"ok": False}
    if cwd:
        ws = persist_workspace_copy(
            cwd,
            file_name=file_name,
            src_binary=dest,
            outline=outline,
            workspace_kind=ws_kind,
        )
        if ws.get("ok"):
            outline["path"] = str(ws.get("path") or "")
    outline["file_name"] = file_name
    put_outline(outline)
    return {
        "bytes": len(data),
        "abs_path": str(dest),
        "workspace": ws,
        "download_url": outline["download_url"],
        "path": outline.get("path") or "",
        "file_name": file_name,
    }


def apply_office_style(doc_id: str, style_id: str) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """Switch style pack, re-render JSON + binary for the same doc_id."""
    outline = _require_doc(doc_id)
    apply_style_to_outline(outline, style_id)
    outline["last_op"] = "style"
    outline["last_ids"] = []
    extra = _materialize(outline)
    extra["style_id"] = outline.get("style_id")
    return outline, extra


def _require_doc(doc_id: str) -> Dict[str, Any]:
    outline = get_outline(str(doc_id or "").strip())
    if not outline:
        raise ValidationAppError(
            f"unknown doc_id `{doc_id}`. Call office_create first and reuse its doc_id."
        )
    return outline


def _tool_payload(outline: Dict[str, Any], extra: Dict[str, Any]) -> Dict[str, Any]:
    compact = compact_outline(outline)
    return {
        "ok": True,
        "doc_id": outline.get("doc_id"),
        "kind": outline.get("kind"),
        "title": outline.get("title"),
        "path": outline.get("path") or "",
        "download_url": outline.get("download_url") or "",
        "file_name": outline.get("file_name") or "",
        "last_op": outline.get("last_op"),
        "appended_ids": outline.get("last_ids") or [],
        "hint": next_hint(outline),
        "outline": compact,
        **extra,
    }


class OfficeToolsPlugin(BasePlugin):
    async def _on_init(self) -> None:
        return None

    async def _on_ready(self) -> None:
        self.manifest.tools = list(TOOLS)

    async def _on_teardown(self) -> None:
        return None

    async def _on_invoke(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        args = arguments if isinstance(arguments, dict) else {}
        try:
            if tool_name == "office_create":
                return self._create(args)
            if tool_name == "office_append":
                return self._append(args)
            if tool_name == "office_revise_plan":
                return self._revise_plan(args)
            if tool_name == "office_replace":
                return self._replace(args)
            if tool_name == "office_save":
                return self._save(args)
        except OfficeOutlineError as exc:
            raise ValidationAppError(str(exc)) from exc
        raise PluginError(f"unknown tool: {tool_name}")

    def _create(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if arguments.get("blocks") or arguments.get("slides") or arguments.get("body"):
            raise ValidationAppError(
                "office_create is the document PLAN only (throughline + title + plan[] + requirements[]). "
                "Write content with office_append, one section/slide at a time."
            )
        through = str(arguments.get("throughline") or arguments.get("thesis") or "").strip()
        if not through:
            raise ValidationAppError(
                "office_create requires throughline (or thesis): one sentence 系统观 before any body."
            )
        outline = empty_outline(
            kind=arguments.get("kind") or "docx",
            title=str(arguments.get("title") or ""),
            subtitle=str(arguments.get("subtitle") or ""),
            author=str(arguments.get("author") or ""),
            plan=arguments.get("plan"),
            requirements=arguments.get("requirements"),
            file_name=str(arguments.get("file_name") or ""),
            throughline=through,
            glossary=arguments.get("glossary") if arguments.get("glossary") is not None else arguments.get("terms"),
            voice=arguments.get("voice"),
            forbidden=arguments.get("forbidden"),
        )
        put_outline(outline)
        extra = _materialize(outline)
        return _tool_payload(outline, extra)

    def _append(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        outline = _require_doc(str(arguments.get("doc_id") or ""))
        outline, appended = apply_append(outline, arguments)
        extra = _materialize(outline)
        extra["appended_ids"] = appended
        return _tool_payload(outline, extra)

    def _revise_plan(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        outline = _require_doc(str(arguments.get("doc_id") or ""))
        outline, added = apply_revise_plan(outline, arguments)
        extra = _materialize(outline)
        extra["added_plan_ids"] = added
        extra["appended_ids"] = outline.get("last_ids") or []
        return _tool_payload(outline, extra)

    def _replace(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        outline = _require_doc(str(arguments.get("doc_id") or ""))
        outline, ids = apply_replace(outline, arguments)
        extra = _materialize(outline)
        extra["appended_ids"] = ids
        return _tool_payload(outline, extra)

    def _save(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        outline = _require_doc(str(arguments.get("doc_id") or ""))
        name = str(arguments.get("file_name") or "").strip()
        if name:
            outline["file_name"] = name
        outline["last_op"] = "save"
        outline["last_ids"] = []
        outline["status"] = "ready"
        outline["writing"] = False
        extra = _materialize(outline)
        return _tool_payload(outline, extra)


def office_tools_manifest() -> PluginManifest:
    return PluginManifest(
        plugin_id="builtin.office",
        name="Office Documents",
        kind="inprocess",
        version="1.0.0",
        description=(
            "Incremental Word/PowerPoint writer (python-docx / python-pptx). "
            "JSON outline is the source of truth; Canvas shows a live preview."
        ),
        enabled=True,
        tools=list(TOOLS),
        config={},
    )
