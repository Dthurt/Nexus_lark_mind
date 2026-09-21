"""LaTeX helpers for Office outlines — extract, pretty-print, OMML for Word."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterator, List, Optional, Tuple
from xml.sax.saxutils import escape

OMML_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
MML_NS = "http://www.w3.org/1998/Math/MathML"

_DISPLAY_ENV = r"(?:equation|align|alignat|gather|multline|displaymath|eqnarray)\*?"

_STANDALONE_MATH = re.compile(
    rf"^\s*(?:"
    rf"\$\$(?P<dd>[\s\S]+?)\$\$"
    rf"|\\\[(?P<br>[\s\S]+?)\\\]"
    rf"|\\\((?P<pr>[\s\S]+?)\\\)"
    rf"|\\begin\{{{_DISPLAY_ENV}\}}(?P<env>[\s\S]+?)\\end\{{{_DISPLAY_ENV}\}}"
    rf"|\$(?P<in>(?:\\.|[^$\n\\])+?)\$"
    rf")\s*$",
    re.S,
)

_INLINE_MATH = re.compile(
    rf"\$\$(?P<dd>[\s\S]+?)\$\$"
    rf"|\\\[(?P<br>[\s\S]+?)\\\]"
    rf"|\\begin\{{{_DISPLAY_ENV}\}}(?P<env>[\s\S]+?)\\end\{{{_DISPLAY_ENV}\}}"
    rf"|\\\((?P<pr>[\s\S]+?)\\\)"
    rf"|(?<!\$)\$(?!\$)(?P<in>(?:\\.|[^$\n\\])+?)\$(?!\$)",
    re.S,
)

_WRAP_MATH = re.compile(
    rf"^\s*(?:\$\$|\\\[|\\\(|\$|\\begin\{{{_DISPLAY_ENV}\}})?"
    rf"(?P<body>[\s\S]*?)"
    rf"(?:\$\$|\\\]|\\\)|\$|\\end\{{{_DISPLAY_ENV}\}})?\s*$",
    re.S,
)

_GREEK = {
    "alpha": "α",
    "beta": "β",
    "gamma": "γ",
    "delta": "δ",
    "epsilon": "ε",
    "varepsilon": "ε",
    "zeta": "ζ",
    "eta": "η",
    "theta": "θ",
    "vartheta": "ϑ",
    "iota": "ι",
    "kappa": "κ",
    "lambda": "λ",
    "mu": "μ",
    "nu": "ν",
    "xi": "ξ",
    "pi": "π",
    "varpi": "ϖ",
    "rho": "ρ",
    "sigma": "σ",
    "varsigma": "ς",
    "tau": "τ",
    "upsilon": "υ",
    "phi": "φ",
    "varphi": "ϕ",
    "chi": "χ",
    "psi": "ψ",
    "omega": "ω",
    "Gamma": "Γ",
    "Delta": "Δ",
    "Theta": "Θ",
    "Lambda": "Λ",
    "Xi": "Ξ",
    "Pi": "Π",
    "Sigma": "Σ",
    "Upsilon": "Υ",
    "Phi": "Φ",
    "Psi": "Ψ",
    "Omega": "Ω",
}

_SYMBOLS = {
    "times": "×",
    "cdot": "·",
    "pm": "±",
    "mp": "∓",
    "leq": "≤",
    "geq": "≥",
    "neq": "≠",
    "approx": "≈",
    "equiv": "≡",
    "sim": "∼",
    "infty": "∞",
    "partial": "∂",
    "nabla": "∇",
    "sum": "∑",
    "prod": "∏",
    "int": "∫",
    "oint": "∮",
    "to": "→",
    "rightarrow": "→",
    "leftarrow": "←",
    "Rightarrow": "⇒",
    "Leftarrow": "⇐",
    "leftrightarrow": "↔",
    "in": "∈",
    "notin": "∉",
    "subset": "⊂",
    "subseteq": "⊆",
    "cup": "∪",
    "cap": "∩",
    "emptyset": "∅",
    "forall": "∀",
    "exists": "∃",
    "cdotp": "·",
    "ast": "∗",
    "star": "⋆",
    "circ": "∘",
    "bullet": "•",
    "ell": "ℓ",
    "hbar": "ℏ",
    "Re": "ℜ",
    "Im": "ℑ",
    "ldots": "…",
    "cdots": "⋯",
    "dots": "…",
    "quad": "  ",
    "qquad": "    ",
    ",": " ",
    ";": " ",
}

_NARY_CHARS = set("∑∏∐∫∬∭∮⋃⋂⋁⋀")

_SUP_CHARS = {
    "0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴",
    "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹",
    "+": "⁺", "-": "⁻", "=": "⁼", "(": "⁽", ")": "⁾",
    "n": "ⁿ", "i": "ⁱ", "x": "ˣ", "y": "ʸ",
    "a": "ᵃ", "b": "ᵇ", "c": "ᶜ", "d": "ᵈ", "e": "ᵉ",
    "f": "ᶠ", "g": "ᵍ", "h": "ʰ", "j": "ʲ", "k": "ᵏ",
    "l": "ˡ", "m": "ᵐ", "o": "ᵒ", "p": "ᵖ", "r": "ʳ",
    "s": "ˢ", "t": "ᵗ", "u": "ᵘ", "v": "ᵛ", "w": "ʷ",
}

_SUB_CHARS = {
    "0": "₀", "1": "₁", "2": "₂", "3": "₃", "4": "₄",
    "5": "₅", "6": "₆", "7": "₇", "8": "₈", "9": "₉",
    "+": "₊", "-": "₋", "=": "₌", "(": "₍", ")": "₎",
    "a": "ₐ", "e": "ₑ", "h": "ₕ", "i": "ᵢ", "j": "ⱼ",
    "k": "ₖ", "l": "ₗ", "m": "ₘ", "n": "ₙ", "o": "ₒ",
    "p": "ₚ", "r": "ᵣ", "s": "ₛ", "t": "ₜ", "u": "ᵤ",
    "v": "ᵥ", "x": "ₓ",
}

_ACCENTS = {
    "^": "^",
    "ˆ": "^",
    "¯": "¯",
    "˜": "~",
    "~": "~",
    "˙": "˙",
    "¨": "¨",
    "→": "→",
}



def _script_unicode(pretty: str, table: dict, prefix: str) -> str:
    raw = str(pretty or "")
    if not raw:
        return ""
    mapped = []
    for ch in raw:
        if ch not in table:
            return f"{prefix}{raw}"
        mapped.append(table[ch])
    return "".join(mapped)


def strip_latex_wrappers(raw: Any) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    m = _STANDALONE_MATH.match(text)
    if m:
        for key in ("dd", "br", "env", "pr", "in"):
            if m.group(key):
                return m.group(key).strip()
    m2 = _WRAP_MATH.match(text)
    body = (m2.group("body") if m2 else text).strip()
    body = re.sub(rf"^\\begin\{{{_DISPLAY_ENV}\}}\s*", "", body)
    body = re.sub(rf"\s*\\end\{{{_DISPLAY_ENV}\}}$", "", body)
    return body.strip()


def extract_standalone_latex(text: Any) -> Optional[Tuple[str, str]]:
    """If *text* is only a math island, return (latex, 'inline'|'block')."""
    raw = str(text or "").strip()
    if not raw:
        return None
    m = _STANDALONE_MATH.match(raw)
    if not m:
        return None
    if m.group("dd") or m.group("br") or m.group("env"):
        latex = (m.group("dd") or m.group("br") or m.group("env") or "").strip()
        return (latex, "block") if latex else None
    latex = (m.group("pr") or m.group("in") or "").strip()
    return (latex, "inline") if latex else None


def iter_text_math_parts(text: Any) -> Iterator[Tuple[str, str]]:
    """Yield ('text', plain) or ('math', latex) segments. Display vs inline via latex_display()."""
    raw = str(text or "")
    if not raw:
        return
    last = 0
    for m in _INLINE_MATH.finditer(raw):
        if m.start() > last:
            yield ("text", raw[last : m.start()])
        latex = (m.group("dd") or m.group("br") or m.group("env") or m.group("pr") or m.group("in") or "").strip()
        if latex:
            kind = "math_block" if (m.group("dd") or m.group("br") or m.group("env")) else "math"
            yield (kind, latex)
        last = m.end()
    if last < len(raw):
        yield ("text", raw[last:])


def text_has_math(text: Any) -> bool:
    raw = str(text or "")
    return bool(_INLINE_MATH.search(raw) or extract_standalone_latex(raw))


def latex_from_block(block: Dict[str, Any]) -> str:
    if not isinstance(block, dict):
        return ""
    return strip_latex_wrappers(
        block.get("latex") or block.get("tex") or block.get("math") or block.get("text") or block.get("content")
    )


def latex_display(block: Dict[str, Any]) -> str:
    raw = str((block or {}).get("display") or (block or {}).get("mode") or "").strip().lower()
    if raw in {"inline", "in-line", "span"}:
        return "inline"
    if raw in {"block", "display", "eq"}:
        return "block"
    return "block"


def latex_to_unicode(tex: str) -> str:
    """Readable fallback for PPT / failed OMML — not a full TeX engine."""
    s = strip_latex_wrappers(tex)
    if not s:
        return ""

    def _group(src: str, i: int) -> Tuple[str, int]:
        if i < len(src) and src[i] == "{":
            depth = 0
            j = i
            while j < len(src):
                if src[j] == "{":
                    depth += 1
                elif src[j] == "}":
                    depth -= 1
                    if depth == 0:
                        return src[i + 1 : j], j + 1
                j += 1
            return src[i + 1 :], len(src)
        if i >= len(src):
            return "", i
        return src[i], i + 1

    def _cmd(src: str, i: int) -> Tuple[str, int]:
        j = i + 1
        if j < len(src) and src[j].isalpha():
            while j < len(src) and src[j].isalpha():
                j += 1
            return src[i + 1 : j], j
        if j < len(src):
            return src[j], j + 1
        return "", j

    out: List[str] = []
    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        if ch == "\\":
            name, i = _cmd(s, i)
            if name in {"left", "right", "big", "Big", "bigg", "Bigg"}:
                if i < n and s[i] in "()[]|.\\":
                    token = s[i]
                    i += 1
                    out.append("" if token == "." else token)
                continue
            if name in {"mathrm", "mathbf", "operatorname", "text", "textrm", "textbf", "mathit"}:
                body, i = _group(s, i)
                out.append(latex_to_unicode(body))
                continue
            if name == "frac":
                num, i = _group(s, i)
                den, i = _group(s, i)
                out.append(f"({latex_to_unicode(num)})/({latex_to_unicode(den)})")
                continue
            if name in {"sqrt", "overline", "hat", "bar", "tilde", "vec", "dot", "ddot"}:
                body, i = _group(s, i)
                inner = latex_to_unicode(body)
                marks = {
                    "sqrt": f"√({inner})",
                    "overline": f"{inner}̄",
                    "hat": f"{inner}̂",
                    "bar": f"{inner}̄",
                    "tilde": f"{inner}̃",
                    "vec": f"{inner}⃗",
                    "dot": f"{inner}̇",
                    "ddot": f"{inner}̈",
                }
                out.append(marks[name])
                continue
            if name in _GREEK:
                out.append(_GREEK[name])
                continue
            if name in _SYMBOLS:
                out.append(_SYMBOLS[name])
                continue
            if name in {"quad", "qquad", ",", ";"}:
                out.append(_SYMBOLS.get(name, " "))
                continue
            if name:
                out.append(name)
            continue
        if ch == "{":
            body, i = _group(s, i)
            out.append(latex_to_unicode(body))
            continue
        if ch == "}":
            i += 1
            continue
        if ch == "^":
            body, i = _group(s, i + 1)
            out.append(_script_unicode(latex_to_unicode(body), _SUP_CHARS, "^"))
            continue
        if ch == "_":
            body, i = _group(s, i + 1)
            out.append(_script_unicode(latex_to_unicode(body), _SUB_CHARS, "_"))
            continue
        if ch == "&":
            out.append("  ")
            i += 1
            continue
        if ch == "\n":
            out.append(" ")
            i += 1
            continue
        out.append(ch)
        i += 1
    return re.sub(r"\s+", " ", "".join(out)).strip()


def _mml_local(tag: str) -> str:
    if tag.startswith("{") and "}" in tag:
        return tag.split("}", 1)[1]
    if tag.startswith("mml:"):
        return tag[4:]
    return tag


def _omml_run(text: str, *, italic: Optional[bool] = None) -> str:
    body = escape(text, {"'": "&apos;", '"': "&quot;"})
    sty = ""
    if italic is False:
        sty = "<m:rPr><m:sty m:val=\"p\"/></m:rPr>"
    elif italic is True:
        sty = "<m:rPr><m:sty m:val=\"i\"/></m:rPr>"
    return f'<m:r>{sty}<m:t xml:space="preserve">{body}</m:t></m:r>'


def _omml_join(parts: List[str]) -> str:
    return "".join(p for p in parts if p)


def _mathml_to_omml_inner(el) -> str:
    name = _mml_local(getattr(el, "tag", "") or "")
    if name in {"math", "mrow", "mstyle", "mpadded", "menclose", "semantics", "none"}:
        kids = [_mathml_to_omml_inner(c) for c in list(el)]
        if name == "semantics" and kids:
            return kids[0]
        return _omml_join(kids)
    if name == "annotation" or name == "annotation-xml":
        return ""
    if name in {"mi", "mn", "mo", "mtext"}:
        text = "".join(el.itertext())
        if text in {"\u2061", "\u2062", "\u2063", "\u2064"}:
            return ""
        italic = True if name == "mi" and len(text) == 1 else False
        if name == "mo":
            italic = False
        return _omml_run(text, italic=italic)
    if name == "mspace":
        return _omml_run(" ")
    if name == "msup":
        kids = list(el)
        base = _mathml_to_omml_inner(kids[0]) if kids else _omml_run("")
        sup = _mathml_to_omml_inner(kids[1]) if len(kids) > 1 else _omml_run("")
        return f"<m:sSup><m:e>{base}</m:e><m:sup>{sup}</m:sup></m:sSup>"
    if name == "msub":
        kids = list(el)
        base = _mathml_to_omml_inner(kids[0]) if kids else _omml_run("")
        sub = _mathml_to_omml_inner(kids[1]) if len(kids) > 1 else _omml_run("")
        return f"<m:sSub><m:e>{base}</m:e><m:sub>{sub}</m:sub></m:sSub>"
    if name in {"msubsup", "munderover"}:
        kids = list(el)
        base_el = kids[0] if kids else None
        base_text = "".join(base_el.itertext()) if base_el is not None else ""
        sub = _mathml_to_omml_inner(kids[1]) if len(kids) > 1 else ""
        sup = _mathml_to_omml_inner(kids[2]) if len(kids) > 2 else ""
        if base_text and any(ch in _NARY_CHARS for ch in base_text):
            chr_ = next((ch for ch in base_text if ch in _NARY_CHARS), base_text[0])
            loc = "undOvr" if name == "munderover" else "subSup"
            return (
                f"<m:nary><m:naryPr><m:chr m:val=\"{escape(chr_)}\"/>"
                f"<m:limLoc m:val=\"{loc}\"/><m:grow m:val=\"1\"/></m:naryPr>"
                f"<m:sub>{sub}</m:sub><m:sup>{sup}</m:sup><m:e/></m:nary>"
            )
        base = _mathml_to_omml_inner(base_el) if base_el is not None else _omml_run("")
        if name == "munderover":
            return (
                f"<m:limUpp><m:e><m:limLow><m:e>{base}</m:e><m:lim>{sub}</m:lim></m:limLow></m:e>"
                f"<m:lim>{sup}</m:lim></m:limUpp>"
            )
        return f"<m:sSubSup><m:e>{base}</m:e><m:sub>{sub}</m:sub><m:sup>{sup}</m:sup></m:sSubSup>"
    if name == "munder":
        kids = list(el)
        return (
            f"<m:limLow><m:e>{_mathml_to_omml_inner(kids[0]) if kids else ''}</m:e>"
            f"<m:lim>{_mathml_to_omml_inner(kids[1]) if len(kids) > 1 else ''}</m:lim></m:limLow>"
        )
    if name == "mover":
        kids = list(el)
        base = _mathml_to_omml_inner(kids[0]) if kids else ""
        acc_el = kids[1] if len(kids) > 1 else None
        acc_text = "".join(acc_el.itertext()) if acc_el is not None else ""
        accent = (el.get("accent") or "").lower() in {"true", "1"}
        if accent or acc_text in _ACCENTS:
            chr_ = _ACCENTS.get(acc_text, acc_text[:1] or "^")
            return f"<m:acc><m:accPr><m:chr m:val=\"{escape(chr_)}\"/></m:accPr><m:e>{base}</m:e></m:acc>"
        over = _mathml_to_omml_inner(acc_el) if acc_el is not None else ""
        return f"<m:limUpp><m:e>{base}</m:e><m:lim>{over}</m:lim></m:limUpp>"
    if name == "mfrac":
        kids = list(el)
        num = _mathml_to_omml_inner(kids[0]) if kids else _omml_run("")
        den = _mathml_to_omml_inner(kids[1]) if len(kids) > 1 else _omml_run("")
        return f"<m:f><m:num>{num}</m:num><m:den>{den}</m:den></m:f>"
    if name == "msqrt":
        inner = _omml_join([_mathml_to_omml_inner(c) for c in list(el)])
        return f"<m:rad><m:radPr><m:degHide m:val=\"1\"/></m:radPr><m:deg/><m:e>{inner}</m:e></m:rad>"
    if name == "mroot":
        kids = list(el)
        base = _mathml_to_omml_inner(kids[0]) if kids else ""
        deg = _mathml_to_omml_inner(kids[1]) if len(kids) > 1 else ""
        return f"<m:rad><m:deg>{deg}</m:deg><m:e>{base}</m:e></m:rad>"
    if name == "mfenced":
        open_c = el.get("open", "(")
        close_c = el.get("close", ")")
        inner = _omml_join([_mathml_to_omml_inner(c) for c in list(el)])
        return (
            f"<m:d><m:dPr><m:begChr m:val=\"{escape(open_c)}\"/>"
            f"<m:endChr m:val=\"{escape(close_c)}\"/></m:dPr><m:e>{inner}</m:e></m:d>"
        )
    if name == "mtable":
        rows = []
        for row in list(el):
            if _mml_local(row.tag) != "mtr":
                continue
            cells = []
            for cell in list(row):
                if _mml_local(cell.tag) != "mtd":
                    continue
                cells.append(f"<m:e>{_omml_join([_mathml_to_omml_inner(c) for c in list(cell)])}</m:e>")
            rows.append(f"<m:mr>{''.join(cells)}</m:mr>")
        return f"<m:m>{''.join(rows)}</m:m>"
    if name in {"mtr", "mtd"}:
        return _omml_join([_mathml_to_omml_inner(c) for c in list(el)])
    if name == "mphantom":
        return ""
    # Unknown: flatten text / children
    kids = list(el)
    if kids:
        return _omml_join([_mathml_to_omml_inner(c) for c in kids])
    text = "".join(el.itertext())
    return _omml_run(text) if text else ""


def _mathml_string_to_omml(mathml: str, *, display: bool) -> str:
    from lxml import etree

    raw = str(mathml or "").strip()
    if not raw:
        raise ValueError("empty mathml")
    if "xmlns" not in raw[:80]:
        raw = raw.replace("<math", f'<math xmlns="{MML_NS}"', 1)
    tree = etree.fromstring(raw.encode("utf-8"))
    inner = _mathml_to_omml_inner(tree)
    if not inner:
        raise ValueError("empty omml")
    if display:
        return (
            f'<m:oMathPara xmlns:m="{OMML_NS}">'
            f'<m:oMathParaPr><m:jc m:val="center"/></m:oMathParaPr>'
            f"<m:oMath>{inner}</m:oMath></m:oMathPara>"
        )
    return f'<m:oMath xmlns:m="{OMML_NS}">{inner}</m:oMath>'


def _simple_latex_omml(tex: str, *, display: bool) -> str:
    """Small subset when latex2mathml is missing or fails."""
    s = strip_latex_wrappers(tex)

    def grp(src: str, i: int) -> Tuple[str, int]:
        if i < len(src) and src[i] == "{":
            depth = 0
            j = i
            while j < len(src):
                if src[j] == "{":
                    depth += 1
                elif src[j] == "}":
                    depth -= 1
                    if depth == 0:
                        return src[i + 1 : j], j + 1
                j += 1
        if i < len(src):
            return src[i], i + 1
        return "", i

    def cmd(src: str, i: int) -> Tuple[str, int]:
        j = i + 1
        if j < len(src) and src[j].isalpha():
            while j < len(src) and src[j].isalpha():
                j += 1
            return src[i + 1 : j], j
        if j < len(src):
            return src[j], j + 1
        return "", j

    def parse_expr(src: str) -> str:
        parts: List[str] = []
        i = 0
        n = len(src)
        while i < n:
            ch = src[i]
            if ch == "\\":
                name, i = cmd(src, i)
                if name in {"left", "right"}:
                    if i < n:
                        i += 1
                    continue
                if name == "frac":
                    a, i = grp(src, i)
                    b, i = grp(src, i)
                    parts.append(f"<m:f><m:num>{parse_expr(a)}</m:num><m:den>{parse_expr(b)}</m:den></m:f>")
                    continue
                if name == "sqrt":
                    a, i = grp(src, i)
                    parts.append(
                        f"<m:rad><m:radPr><m:degHide m:val=\"1\"/></m:radPr><m:deg/><m:e>{parse_expr(a)}</m:e></m:rad>"
                    )
                    continue
                if name in _GREEK:
                    parts.append(_omml_run(_GREEK[name], italic=True))
                    continue
                if name in _SYMBOLS:
                    parts.append(_omml_run(_SYMBOLS[name], italic=False))
                    continue
                if name in {"mathrm", "mathbf", "text", "operatorname"}:
                    a, i = grp(src, i)
                    parts.append(_omml_run(a, italic=False))
                    continue
                if name:
                    parts.append(_omml_run(name, italic=False))
                continue
            if ch == "{":
                body, i = grp(src, i)
                parts.append(parse_expr(body))
                continue
            if ch in "^_":
                first = ch
                body1, i = grp(src, i + 1)
                while i < n and src[i] in " \t":
                    i += 1
                if i < n and src[i] in "^_" and src[i] != first:
                    body2, i = grp(src, i + 1)
                    base = parts.pop() if parts else _omml_run("")
                    sub_b, sup_b = (body1, body2) if first == "_" else (body2, body1)
                    parts.append(
                        f"<m:sSubSup><m:e>{base}</m:e><m:sub>{parse_expr(sub_b)}</m:sub>"
                        f"<m:sup>{parse_expr(sup_b)}</m:sup></m:sSubSup>"
                    )
                else:
                    base = parts.pop() if parts else _omml_run("")
                    if first == "^":
                        parts.append(f"<m:sSup><m:e>{base}</m:e><m:sup>{parse_expr(body1)}</m:sup></m:sSup>")
                    else:
                        parts.append(f"<m:sSub><m:e>{base}</m:e><m:sub>{parse_expr(body1)}</m:sub></m:sSub>")
                continue
            if ch in " \n\t":
                i += 1
                continue
            if ch in "()[]|":
                parts.append(_omml_run(ch, italic=False))
                i += 1
                continue
            parts.append(_omml_run(ch, italic=ch.isalpha()))
            i += 1
        return _omml_join(parts) or _omml_run("")

    inner = parse_expr(s)
    if display:
        return (
            f'<m:oMathPara xmlns:m="{OMML_NS}">'
            f'<m:oMathParaPr><m:jc m:val="center"/></m:oMathParaPr>'
            f"<m:oMath>{inner}</m:oMath></m:oMathPara>"
        )
    return f'<m:oMath xmlns:m="{OMML_NS}">{inner}</m:oMath>'


def latex_to_omml_xml(tex: str, *, display: bool = True) -> Optional[str]:
    latex = strip_latex_wrappers(tex)
    if not latex:
        return None
    try:
        from latex2mathml.converter import convert

        try:
            mathml = convert(latex, display="block" if display else "inline")
        except TypeError:
            mathml = convert(latex)
        return _mathml_string_to_omml(mathml, display=display)
    except Exception:
        try:
            return _simple_latex_omml(latex, display=display)
        except Exception:
            return None


def latex_to_omml_element(tex: str, *, display: bool = True):
    xml = latex_to_omml_xml(tex, display=display)
    if not xml:
        return None
    try:
        from docx.oxml import parse_xml
        from docx.oxml.ns import nsmap

        if "m" not in nsmap:
            nsmap["m"] = OMML_NS
        return parse_xml(xml)
    except Exception:
        return None


def ppt_math_alternate_xml(tex: str) -> Optional[str]:
    """Do not emit a14:m / AlternateContent. PowerPoint repairs that slide XML."""
    return None


def equation_fallback_lines(tex: str) -> Tuple[str, str]:
    pretty = latex_to_unicode(tex)
    source = strip_latex_wrappers(tex)
    return pretty or source, source
