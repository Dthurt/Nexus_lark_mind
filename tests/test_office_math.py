from zipfile import ZipFile

from lxml import etree

from src.core_kernel.plugin_runtime.office_math import (
    iter_text_math_parts,
    latex_export_warnings,
    latex_to_omml_xml,
    latex_to_unicode,
    text_has_math,
)
from src.core_kernel.plugin_runtime.office_outline import apply_append, empty_outline
from src.core_kernel.plugin_runtime.office_style import apply_style_to_outline
from src.core_kernel.plugin_runtime.office_writer import render_docx, render_pptx

from tests.test_office_writer import _xml_join

_A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
_ALLOWED_P_KIDS = {"pPr", "r", "br", "fld", "endParaRPr"}
_BROKEN_PPT_MARKERS = (
    'xmlns:ns0="http://www.w3.org/2000/xmlns/"',
    "ns0:a14=",
    "ns0:mc=",
    "a14:m",
    "AlternateContent",
)


def _slide_xmls(data: bytes):
    with ZipFile(__import__("io").BytesIO(data)) as zf:
        names = [n for n in zf.namelist() if n.startswith("ppt/slides/slide") and n.endswith(".xml")]
        return [(name, zf.read(name)) for name in names]


def _assert_pptx_slides_wellformed(data: bytes) -> str:
    joined = []
    for name, raw in _slide_xmls(data):
        text = raw.decode("utf-8")
        joined.append(text)
        for marker in _BROKEN_PPT_MARKERS:
            assert marker not in text, f"{name} still contains {marker}"
        root = etree.fromstring(raw)
        for para in root.xpath(f'//*[local-name()="p" and namespace-uri()="{_A_NS}"]'):
            kids = [c.tag.split("}")[-1] for c in para]
            unexpected = [k for k in kids if k not in _ALLOWED_P_KIDS]
            assert not unexpected, f"{name} a:p has unexpected children {unexpected}"
            if "endParaRPr" in kids:
                assert kids[-1] == "endParaRPr", f"{name} has content after a:endParaRPr"
    return "\n".join(joined)


def test_unicode_keeps_letter_subscripts():
    assert latex_to_unicode(r"\mu_x") == "μₓ"
    assert latex_to_unicode(r"x^2") == "x²"
    assert latex_to_unicode(r"\theta_i") == "θᵢ"


def test_iter_splits_inline_islands():
    parts = list(iter_text_math_parts(r"均值 $\mu_x$ 满足。"))
    assert parts == [("text", "均值 "), ("math", r"\mu_x"), ("text", " 满足。")]
    assert text_has_math(r"均值 $\mu_x$")


def test_inline_omml_is_not_a_display_paragraph():
    xml = latex_to_omml_xml(r"\mu_x", display=False)
    assert xml
    assert "oMathPara" not in xml
    assert "oMath" in xml
    assert "sSub" in xml


def test_docx_inline_math_embeds_omml():
    out = empty_outline(kind="docx", title="公式", throughline="内联公式", plan=["公式"])
    out, _ = apply_append(
        out,
        {
            "plan_id": "p1",
            "blocks": [
                {"type": "heading", "level": 2, "text": r"公式 $\mu_x$", "req": "p1"},
                {"type": "paragraph", "text": r"均值 $\mu_x$ 满足 $x^2+y^2=1$。", "req": "p1"},
            ],
        },
    )
    xml = _xml_join(render_docx(out), "word/")
    assert "oMath" in xml
    assert xml.count("oMathPara") == 0
    assert "均值" in xml
    assert "满足" in xml


def test_pptx_inline_math_keeps_neighbors():
    out = empty_outline(kind="pptx", title="公式", throughline="内联公式", plan=["公式"])
    out, _ = apply_append(
        out,
        {
            "plan_id": "p1",
            "slides": [
                {
                    "type": "bullets",
                    "title": "公式",
                    "items": [r"均值 $\mu_x$ 满足约束。"],
                    "req": "p1",
                }
            ],
        },
    )
    data = render_pptx(out)
    xml = _assert_pptx_slides_wellformed(data)
    assert "均值" in xml
    assert "满足约束" in xml
    assert "μₓ" in xml
    assert "Cambria Math" in xml


def _maxwell_like_outline(style_id: str):
    out = empty_outline(kind="pptx", title="麦克斯韦方程组", throughline="公式页", plan=["方程"])
    apply_style_to_outline(out, style_id)
    out["slides"] = [
        {"type": "section", "title": "麦克斯韦方程组", "kicker": "Part 1"},
        {
            "type": "equation",
            "title": "高斯定理",
            "latex": r"\nabla \cdot \mathbf{E} = \frac{\rho}{\varepsilon_0}",
        },
        {
            "type": "bullets",
            "title": "要点",
            "items": [
                r"电场散度 $\nabla \cdot E = \rho/\varepsilon_0$",
                r"磁场无散 $\nabla \cdot B = 0$",
                r"真空磁导率 $\mu_0$",
            ],
        },
        {
            "type": "two_column",
            "title": "对照",
            "left": {
                "heading": "微分",
                "items": [r"$\nabla\cdot\mathbf{B}=0$", r"常数 $\mu$"],
            },
            "right": {
                "heading": "积分",
                "body": r"通量与环量",
                "items": [r"$\oint$ 与 $\mu_0$"],
            },
        },
    ]
    return out


def test_pptx_math_deck_parses_without_a14_alternate():
    for style_id in ("commercial", "academic"):
        data = render_pptx(_maxwell_like_outline(style_id))
        xml = _assert_pptx_slides_wellformed(data)
        assert "麦克斯韦方程组" in xml
        assert "高斯定理" in xml
        assert "电场散度" in xml
        assert "磁场无散" in xml
        assert "对照" in xml
        assert "μ" in xml
        assert "∇" in xml or "ρ" in xml
        assert "Cambria Math" in xml


def test_latex_export_warnings_flag_ppt_and_complex_envs():
    assert "ppt-unicode" in latex_export_warnings(r"\mu_x", target="pptx")
    assert "complex" in latex_export_warnings(r"\begin{align} a \\ b \end{align}", target="docx")
    assert latex_export_warnings("", target="docx") == []
