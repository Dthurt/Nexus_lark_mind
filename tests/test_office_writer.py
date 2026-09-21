from zipfile import ZipFile

from src.core_kernel.plugin_runtime.office_outline import apply_append, empty_outline
from src.core_kernel.plugin_runtime.office_style import apply_style_to_outline
from src.core_kernel.plugin_runtime.office_writer import render_docx, render_pptx


def _xml_join(path_bytes: bytes, prefix: str) -> str:
    parts = []
    with ZipFile(__import__("io").BytesIO(path_bytes)) as zf:
        for name in zf.namelist():
            if name.startswith(prefix) and name.endswith(".xml"):
                parts.append(zf.read(name).decode("utf-8", errors="replace"))
    return "\n".join(parts)


def test_docx_contains_styled_blocks():
    out = empty_outline(kind="docx", title="季度方案", subtitle="Q3", throughline="先对齐结构", plan=["背景", "预算"])
    out, _ = apply_append(
        out,
        {
            "plan_id": "p1",
            "blocks": [
                {"type": "heading", "level": 2, "text": "背景", "req": "p1"},
                {"type": "quote", "text": "先对齐结构，再写正文。", "attribution": "NLM"},
                {
                    "type": "table",
                    "headers": ["项", "值"],
                    "rows": [["预算", "120"]],
                },
            ]
        },
    )
    out, _ = apply_append(
        out,
        {
            "plan_id": "p2",
            "blocks": [
                {"type": "page_break"},
                {"type": "heading", "level": 2, "text": "预算", "req": "p2"},
                {"type": "bullet_list", "items": ["人力", "渠道"], "req": "p2"},
            ]
        },
    )
    data = render_docx(out)
    assert data[:2] == b"PK"
    xml = _xml_join(data, "word/")
    assert "季度方案" in xml
    assert "背景" in xml
    assert "预算" in xml
    assert "人力" in xml
    assert "2A9D8F" in xml or "1D7A70" in xml


def test_pptx_contains_slide_types():
    out = empty_outline(kind="pptx", title="Kickoff", subtitle="Q3 启动", throughline="先讲目标", plan=["目标", "对比"])
    out, _ = apply_append(
        out,
        {
            "slides": [
                {
                    "type": "section",
                    "title": "目标",
                    "kicker": "Part 1",
                    "req": "p1",
                    "notes": "先讲增长",
                }
            ]
        },
    )
    out, _ = apply_append(
        out,
        {
            "slides": [
                {
                    "type": "two_column",
                    "title": "对比",
                    "left": {"heading": "现状", "items": ["慢"]},
                    "right": {"heading": "目标", "items": ["快"]},
                    "req": "p2",
                }
            ]
        },
    )
    data = render_pptx(out)
    assert data[:2] == b"PK"
    xml = _xml_join(data, "ppt/slides/")
    assert "Kickoff" in xml
    assert "目标" in xml
    assert "对比" in xml
    notes = _xml_join(data, "ppt/notesSlides/")
    assert "先讲增长" in notes


def test_docx_equation_writes_omml_or_fallback():
    out = empty_outline(kind="docx", title="公式", throughline="把公式写清楚", plan=["公式"])
    out, _ = apply_append(
        out,
        {
            "plan_id": "p1",
            "blocks": [
                {"type": "heading", "level": 2, "text": "公式", "req": "p1"},
                {"type": "equation", "latex": r"E = mc^2", "req": "p1"},
                {"type": "paragraph", "text": r"损失为 $$\frac{a}{b}$$ 。", "req": "p1"},
            ],
        },
    )
    data = render_docx(out)
    xml = _xml_join(data, "word/")
    assert "oMath" in xml or "E = mc" in xml or "mc^2" in xml
    assert "frac" in xml or "a" in xml


def test_pptx_equation_slide_is_readable():
    out = empty_outline(kind="pptx", title="公式", throughline="公式页", plan=["公式"])
    out, _ = apply_append(
        out,
        {
            "plan_id": "p1",
            "slides": [{"type": "equation", "title": "公式", "latex": r"E = mc^2", "req": "p1"}],
        },
    )
    data = render_pptx(out)
    xml = _xml_join(data, "ppt/slides/")
    assert "E = mc" in xml or "mc²" in xml or "mc^2" in xml or "公式" in xml


def test_academic_docx_uses_times_not_teal_bar():
    out = empty_outline(kind="docx", title="论文", throughline="先定义再证明", plan=["方法"])
    apply_style_to_outline(out, "academic")
    out, _ = apply_append(
        out,
        {
            "plan_id": "p1",
            "blocks": [
                {"type": "heading", "level": 2, "text": "方法", "req": "p1"},
                {"type": "quote", "text": "引用一句。"},
                {"type": "table", "headers": ["项", "值"], "rows": [["n", "1"]]},
                {"type": "equation", "latex": r"E = mc^2", "req": "p1"},
            ],
        },
    )
    xml = _xml_join(render_docx(out), "word/")
    assert "Times" in xml
    assert "2A9D8F" not in xml
    assert "表 1" in xml
    assert "(1)" in xml


def test_academic_pptx_section_is_white_not_dark_fill():
    out = empty_outline(kind="pptx", title="Seminar", throughline="先讲问题", plan=["问题"])
    apply_style_to_outline(out, "academic")
    out, _ = apply_append(
        out,
        {
            "plan_id": "p1",
            "slides": [{"type": "section", "title": "问题", "kicker": "Part 1", "req": "p1"}],
        },
    )
    xml = _xml_join(render_pptx(out), "ppt/slides/")
    assert "Times" in xml or "01" in xml
    assert "1D7A70" not in xml
    assert "2A9D8F" not in xml
    assert "FFFFFF" in xml


def test_commercial_pptx_section_keeps_dark_fill():
    out = empty_outline(kind="pptx", title="Kickoff", throughline="先讲目标", plan=["目标"])
    out, _ = apply_append(
        out,
        {
            "plan_id": "p1",
            "slides": [{"type": "section", "title": "目标", "kicker": "Part 1", "req": "p1"}],
        },
    )
    xml = _xml_join(render_pptx(out), "ppt/slides/")
    assert "1D7A70" in xml or "2A9D8F" in xml
