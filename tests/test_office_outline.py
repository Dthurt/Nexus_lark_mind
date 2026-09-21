from src.core_kernel.plugin_runtime.office_outline import (
    OfficeOutlineError,
    alignment_report,
    apply_append,
    apply_replace,
    apply_revise_plan,
    compact_outline,
    empty_outline,
    next_hint,
    normalize_block,
    normalize_kind,
    parse_outline,
)
import pytest


def test_normalize_kind_aliases():
    assert normalize_kind("word") == "docx"
    assert normalize_kind("ppt") == "pptx"
    with pytest.raises(OfficeOutlineError):
        normalize_kind("pdf")


def test_create_requires_plan_and_builds_cover():
    with pytest.raises(OfficeOutlineError):
        empty_outline(kind="docx", title="X", plan=[], throughline="x")
    with pytest.raises(OfficeOutlineError, match="throughline"):
        empty_outline(kind="docx", title="X", plan=["背景"])
    out = empty_outline(
        kind="docx",
        title="季度方案",
        subtitle="Q3",
        throughline="增长必须先对齐交付节奏",
        plan=[{"id": "p1", "title": "背景", "maps_to": "说明背景"}, {"id": "p2", "title": "目标"}],
        requirements=[{"id": "r1", "text": "说明背景", "mapped_to": "p1"}],
        glossary=[{"term": "交付节奏", "meaning": "从需求到上线的周期"}],
    )
    assert out["schema"] == "nlm.office.v1"
    assert out["kind"] == "docx"
    assert out["doc_id"].startswith("off_")
    types = [b["type"] for b in out["blocks"]]
    assert "heading" in types
    assert "numbered_list" in types
    assert out["last_op"] == "create"
    assert out["throughline"] == "增长必须先对齐交付节奏"
    assert out["glossary"][0]["term"] == "交付节奏"
    assert any(b.get("id") == "cover_throughline" for b in out["blocks"])


def test_append_and_replace_word():
    out = empty_outline(kind="docx", title="Memo", throughline="先写背景再下结论", plan=["背景", "结论"])
    out, ids = apply_append(
        out,
        {
            "blocks": [
                {"type": "heading", "level": 2, "text": "背景", "req": "p1"},
                {"type": "paragraph", "text": "市场变化加快。", "req": "p1"},
                {
                    "type": "table",
                    "headers": ["项", "值"],
                    "rows": [["预算", "120"]],
                    "req": "p1",
                },
            ]
        },
    )
    assert len(ids) == 3
    assert any(b["type"] == "table" for b in out["blocks"])
    target = ids[1]
    out, rid = apply_replace(
        out,
        {"id": target, "block": {"type": "paragraph", "text": "修订后的背景。", "req": "p1"}},
    )
    assert rid == [target]
    hit = next(b for b in out["blocks"] if b["id"] == target)
    assert hit["text"].startswith("修订")


def test_append_rejects_giant_blob_and_wrong_kind():
    out = empty_outline(kind="docx", title="X", throughline="一条主线", plan=["A"])
    too_many = [{"type": "paragraph", "text": f"p{i}"} for i in range(12)]
    with pytest.raises(OfficeOutlineError, match="at most"):
        apply_append(out, {"blocks": too_many})
    ppt = empty_outline(kind="pptx", title="Deck", throughline="一条主线", plan=["开场"])
    with pytest.raises(OfficeOutlineError, match="PowerPoint"):
        apply_append(ppt, {"blocks": [{"type": "paragraph", "text": "nope"}]})


def test_ppt_append_and_alignment():
    out = empty_outline(
        kind="pptx",
        title="Kickoff",
        throughline="先讲目标再讲节奏",
        plan=[{"id": "p1", "title": "目标"}, {"id": "p2", "title": "节奏"}],
        requirements=[{"id": "r1", "text": "讲清目标", "mapped_to": "p1"}],
    )
    assert out["slides"][0]["type"] == "title"
    out, ids = apply_append(
        out,
        {
            "slides": [
                {
                    "type": "bullets",
                    "title": "目标",
                    "items": ["增长", "质量"],
                    "notes": "强调质量",
                    "req": "p1",
                }
            ]
        },
    )
    assert ids
    align = alignment_report(out)
    assert align["filled_plan"] >= 1
    compact = compact_outline(out)
    assert compact["counts"]["slides"] >= 2
    hint = next_hint(out)
    assert "office_append" in hint or "office_save" in hint


def test_system_prompt_forces_office_alignment():
    from src.core_kernel.agent_prompts import build_system_prompt

    text = build_system_prompt(metadata={"cwd": "E:/tmp"})
    assert "office_create" in text
    assert "office_append" in text
    assert "office_revise_plan" in text
    assert "throughline" in text
    assert "requirements" in text
    assert "giant blob" in text or "dump" in text
    assert "style-blind" in text or "花哨" in text
    assert "theme" in text


def test_parse_outline_roundtrip():
    raw = empty_outline(kind="docx", title="A", throughline="主线", plan=["S1"])
    parsed = parse_outline(raw)
    assert parsed["kind"] == "docx"
    assert parsed["plan"][0]["title"] == "S1"
    assert parsed["throughline"] == "主线"
    assert parsed["style_id"] == "commercial"
    assert parsed["theme"]["accent"] == "#2A9D8F"


def test_equation_block_and_dollar_paragraph():
    eq = normalize_block({"type": "equation", "latex": r"E = mc^2", "display": "block"})
    assert eq["type"] == "equation"
    assert eq["latex"] == "E = mc^2"
    assert eq["display"] == "block"
    promoted = normalize_block({"type": "paragraph", "text": r"$$\frac{a}{b}$$"})
    assert promoted["type"] == "equation"
    assert promoted["latex"] == r"\frac{a}{b}"
    assert promoted["display"] == "block"
    inline = normalize_block({"type": "math", "latex": r"\mu_x", "display": "inline"})
    assert inline["type"] == "equation" and inline["display"] == "inline"


def test_append_requires_plan_id_and_rejects_unknown():
    out = empty_outline(kind="docx", title="Memo", throughline="主线", plan=["背景", "结论"])
    with pytest.raises(OfficeOutlineError, match="plan_id"):
        apply_append(out, {"blocks": [{"type": "paragraph", "text": "没有归属"}]})
    with pytest.raises(OfficeOutlineError, match="unknown plan_id"):
        apply_append(out, {"plan_id": "p99", "blocks": [{"type": "paragraph", "text": "错节"}]})


def test_append_rejects_early_conclusion_and_new_heading():
    out = empty_outline(
        kind="docx",
        title="Memo",
        throughline="先背景后结论",
        plan=[{"id": "p1", "title": "背景"}, {"id": "p2", "title": "结论"}],
    )
    with pytest.raises(OfficeOutlineError, match="conclusion"):
        apply_append(
            out,
            {
                "plan_id": "p2",
                "blocks": [
                    {"type": "heading", "level": 2, "text": "结论"},
                    {"type": "paragraph", "text": "太早了。"},
                ],
            },
        )
    with pytest.raises(OfficeOutlineError, match="not on the document plan"):
        apply_append(
            out,
            {
                "plan_id": "p1",
                "blocks": [
                    {"type": "heading", "level": 2, "text": "全新章节"},
                    {"type": "paragraph", "text": "不该出现。"},
                ],
            },
        )


def test_revise_plan_adds_section_then_append_updates_last_block():
    out = empty_outline(
        kind="docx",
        title="Memo",
        throughline="增长先对齐节奏",
        plan=["背景"],
        glossary=[{"term": "节奏", "meaning": "交付周期"}],
    )
    out, added = apply_revise_plan(out, {"add": [{"id": "p2", "title": "动作", "maps_to": "下一步"}]})
    assert added == ["p2"]
    assert any(r["id"] == "p2" for r in out["plan"])
    cover = next(b for b in out["blocks"] if b.get("id") == "cover_plan")
    assert any("动作" in str(x) for x in cover.get("items") or [])
    out, ids = apply_append(
        out,
        {
            "plan_id": "p1",
            "bridge": "承接封面的主线，先把背景说清。",
            "blocks": [
                {"type": "heading", "level": 2, "text": "背景"},
                {"type": "paragraph", "text": "市场变化加快。节奏决定胜负。"},
                {"type": "equation", "latex": r"L = \sum_i \ell_i"},
            ],
        },
    )
    assert ids
    assert out["last_block"]["plan_id"] == "p1"
    assert "市场变化" in (out["last_block"].get("excerpt") or "")
    assert out["plan"][0]["status"] == "done"
    compact = compact_outline(out)
    assert compact["throughline"]
    assert compact["last_block"]["plan_id"] == "p1"
    hint = next_hint(out)
    assert "p2" in hint and "plan_id" in hint


def test_default_style_id_is_commercial_and_unknown_falls_back():
    out = empty_outline(kind="docx", title="Memo", throughline="主线", plan=["背景"])
    assert out["style_id"] == "commercial"
    assert out["theme"]["accent"] == "#2A9D8F"
    assert out["theme"]["font_body"] == "Calibri"
    parsed = parse_outline({**out, "style_id": "unknown-pack", "theme": {"accent": "#FF0000"}})
    assert parsed["style_id"] == "commercial"
    assert parsed["theme"]["accent"] == "#2A9D8F"
    academic = parse_outline({**out, "style_id": "academic", "theme": {"accent": "#FF0000"}})
    assert academic["style_id"] == "academic"
    assert academic["theme"]["font_body"] == "Times New Roman"
    assert academic["theme"]["paper"] == "#FFFFFF"
    compact = compact_outline(academic)
    assert "style_id" not in compact
    assert "theme" not in compact
