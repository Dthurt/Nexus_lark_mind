"""File → text helpers for KB ingest (md/txt/rst + PDF/Office)."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import List, Optional, Tuple

TEXT_SUFFIXES = {".md", ".markdown", ".txt", ".rst", ".org", ".mdx"}
HTML_SUFFIXES = {".html", ".htm"}
PDF_SUFFIXES = {".pdf"}
OFFICE_SUFFIXES = {".docx", ".xlsx", ".pptx"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
SUPPORTED_SUFFIXES = TEXT_SUFFIXES | HTML_SUFFIXES | PDF_SUFFIXES | OFFICE_SUFFIXES | IMAGE_SUFFIXES

# Composer session chips stay small; library ingest / workspace sync use the 20MB default.
MAX_SESSION_UPLOAD_BYTES = 512_000
DEFAULT_LIBRARY_INGEST_BYTES = 20 * 1024 * 1024
DEFAULT_PDF_MAX_PAGES = 400
# Backward-compatible name: library default (was 512KB).
MAX_INGEST_BYTES = DEFAULT_LIBRARY_INGEST_BYTES


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        val = int(raw)
    except ValueError:
        return default
    return max(minimum, min(val, maximum))


def library_ingest_max_bytes() -> int:
    """Library file ingest / workspace sync cap. Env ``KB_INGEST_MAX_BYTES``."""
    return _env_int(
        "KB_INGEST_MAX_BYTES",
        DEFAULT_LIBRARY_INGEST_BYTES,
        minimum=1024,
        maximum=100 * 1024 * 1024,
    )


def pdf_max_pages() -> int:
    """Max PDF pages to extract. Env ``KB_PDF_MAX_PAGES``."""
    return _env_int("KB_PDF_MAX_PAGES", DEFAULT_PDF_MAX_PAGES, minimum=1, maximum=5000)


def ocr_enabled() -> bool:
    raw = (os.getenv("KB_OCR") or "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def html_to_text(raw_html: str) -> str:
    """Strip tags / scripts from HTML for library ingest."""
    from html.parser import HTMLParser

    class _Strip(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self._skip = 0
            self.parts: List[str] = []

        def handle_starttag(self, tag: str, attrs) -> None:  # type: ignore[override]
            t = (tag or "").lower()
            if t in {"script", "style", "noscript"}:
                self._skip += 1
            elif t in {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "tr", "section", "article"}:
                self.parts.append("\n")

        def handle_endtag(self, tag: str) -> None:  # type: ignore[override]
            t = (tag or "").lower()
            if t in {"script", "style", "noscript"} and self._skip:
                self._skip -= 1
            elif t in {"p", "div", "li", "h1", "h2", "h3", "h4", "tr", "section", "article"}:
                self.parts.append("\n")

        def handle_data(self, data: str) -> None:  # type: ignore[override]
            if self._skip:
                return
            text = (data or "").strip()
            if text:
                self.parts.append(text)

    parser = _Strip()
    try:
        parser.feed(raw_html or "")
        parser.close()
    except Exception:
        text = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", raw_html or "")
        text = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", text)
        text = re.sub(r"<[^>]+>", " ", text)
        return re.sub(r"\s+", " ", text).strip()
    body = " ".join(parser.parts)
    body = re.sub(r"[ \t]{2,}", " ", body)
    body = re.sub(r"\n{3,}", "\n\n", body)
    return body.strip()


def is_ingestible(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_SUFFIXES


def read_file_as_text(
    path: Path, *, max_bytes: Optional[int] = None
) -> Tuple[str, str]:
    """Return (text, note). note is empty on success; non-empty explains degrade."""
    raw = path.read_bytes()
    return read_bytes_as_text(raw, path.suffix, filename=path.name, max_bytes=max_bytes)


def read_bytes_as_text(
    raw: bytes,
    suffix: str,
    *,
    filename: str = "",
    max_bytes: Optional[int] = None,
) -> Tuple[str, str]:
    """Same extractors as ``read_file_as_text`` but from in-memory bytes."""
    limit = library_ingest_max_bytes() if max_bytes is None else max_bytes
    if len(raw) > limit:
        raise ValueError(f"file too large ({len(raw)} bytes, max {limit})")
    suffix = (suffix or "").lower()
    if not suffix.startswith("."):
        suffix = f".{suffix}" if suffix else ""
    name = filename or f"upload{suffix}"
    if suffix in IMAGE_SUFFIXES:
        return (
            f"![image]({name})\n\n"
            f"Visual document: {name}\n",
            "image-placeholder",
        )
    if suffix in HTML_SUFFIXES:
        try:
            html = raw.decode("utf-8", errors="replace")
        except Exception:
            html = raw.decode("latin-1", errors="replace")
        text = html_to_text(html)
        if not text.strip():
            raise ValueError("HTML produced no extractable text")
        return text, "extracted via html"
    if suffix in PDF_SUFFIXES:
        text, note = _extract_pdf(raw, filename=name)
        if not text.strip():
            raise ValueError(note or "PDF produced no extractable text")
        return text, note
    if suffix in OFFICE_SUFFIXES:
        text, note = _extract_office(raw, suffix)
        if not text.strip():
            raise ValueError(note or f"{suffix} produced no extractable text")
        return text, note
    text = raw.decode("utf-8", errors="replace")
    if text.startswith("\ufeff"):
        text = text[1:]
    return text, ""


_CID_TOKEN_RE = re.compile(r"\(cid:\d+\)", re.IGNORECASE)
_MOJIBAKE_MARKERS = (
    "锟斤拷",
    "ä¸",
    "äº",
    "å­",
    "æ–",
    "çš",
    "è¿",
    "Ã©",
    "Â\xa0",
)


def _is_cjk_char(ch: str) -> bool:
    code = ord(ch)
    return (
        0x3400 <= code <= 0x4DBF
        or 0x4E00 <= code <= 0x9FFF
        or 0xF900 <= code <= 0xFAFF
        or 0x3040 <= code <= 0x30FF
        or 0xAC00 <= code <= 0xD7AF
        or 0xFF00 <= code <= 0xFFEF
    )


def _cjk_count(text: str) -> int:
    return sum(1 for ch in text if _is_cjk_char(ch))


def _join_pdf_pages(parts: List[str]) -> str:
    return "\n\n".join(p.strip() for p in parts if p and p.strip())


def _pdf_text_is_garbled(text: str, *, hint: str = "") -> bool:
    """True when extract looks like mojibake, CID leftovers, or binary scrape."""
    blob = (text or "").strip()
    if not blob:
        return False
    sample = blob[:12000]
    n = len(sample)
    if n < 8:
        return False
    repl = sample.count("\ufffd")
    cjk = _cjk_count(sample)
    pua = sum(1 for ch in sample if 0xE000 <= ord(ch) <= 0xF8FF)
    cid_hits = len(_CID_TOKEN_RE.findall(sample))
    if repl / n >= 0.04:
        return True
    if cid_hits >= 3:
        return True
    if pua / n >= 0.08:
        return True
    printable = sum(1 for ch in sample if ch.isprintable() or ch in "\n\t\r")
    if printable / n < 0.75:
        return True
    high_latin = sum(
        1 for ch in sample if 0x80 <= ord(ch) <= 0x024F and not _is_cjk_char(ch)
    )
    if n >= 40 and high_latin / n >= 0.12 and cjk / n < 0.02:
        return True
    moji = sum(sample.count(marker) for marker in _MOJIBAKE_MARKERS)
    ascii_letters = sum(1 for ch in sample if "a" <= ch.lower() <= "z")
    if moji >= 6 and cjk / n < 0.05 and ascii_letters / n < 0.45:
        return True
    hint_cjk = _cjk_count(hint or "")
    if hint_cjk >= 2 and n >= 24 and cjk < 2 and ascii_letters / n < 0.35:
        return True
    return False


def _accept_pdf_text(
    text: str, note: str, *, hint: str, notes: List[str]
) -> Optional[Tuple[str, str]]:
    cleaned = (text or "").strip()
    if not cleaned:
        if note:
            notes.append(note)
        return None
    if _pdf_text_is_garbled(cleaned, hint=hint):
        notes.append(f"{note or 'extractor'} looked garbled")
        return None
    return cleaned, note


def _pymupdf_mod():
    try:
        import pymupdf  # type: ignore

        return pymupdf
    except ImportError:
        try:
            import fitz as pymupdf  # type: ignore

            return pymupdf
        except ImportError:
            return None


def _pypdf_extract(raw: bytes) -> Tuple[str, str]:
    try:
        from pypdf import PdfReader  # type: ignore
        import io

        reader = PdfReader(io.BytesIO(raw))
        parts: List[str] = []
        for page in reader.pages[: pdf_max_pages()]:
            try:
                parts.append(page.extract_text() or "")
            except Exception:
                continue
        text = _join_pdf_pages(parts)
        if text:
            return text, "extracted via pypdf"
        return "", "pypdf produced no text"
    except ImportError:
        return "", "pypdf unavailable"
    except Exception as exc:
        return "", f"pypdf failed: {exc}"


def _pymupdf_extract(raw: bytes) -> Tuple[str, str]:
    """Embedded text via MuPDF (CID / CJK ToUnicode maps that pypdf often misses)."""
    mod = _pymupdf_mod()
    if mod is None:
        return "", "pymupdf unavailable"
    try:
        doc = mod.open(stream=raw, filetype="pdf")
    except Exception as exc:
        return "", f"pymupdf open failed: {exc}"
    try:
        parts: List[str] = []
        limit = pdf_max_pages()
        for i, page in enumerate(doc):
            if i >= limit:
                break
            try:
                parts.append(page.get_text("text") or "")
            except Exception:
                continue
        text = _join_pdf_pages(parts)
        if text:
            return text, "extracted via pymupdf"
        return "", "pymupdf produced no text"
    finally:
        try:
            doc.close()
        except Exception:
            pass


def _extract_pdf(raw: bytes, *, filename: str = "") -> Tuple[str, str]:
    """pypdf → pymupdf text → language-like crude scrape → OCR last."""
    hint = filename or ""
    notes: List[str] = []
    for extractor in (_pypdf_extract, _pymupdf_extract, _crude_pdf_text, _ocr_pdf):
        accepted = _accept_pdf_text(*extractor(raw), hint=hint, notes=notes)
        if accepted:
            return accepted
    detail = "; ".join(notes) if notes else "no extractor produced text"
    return "", f"PDF produced no extractable text ({detail})"


def _ocr_engine():
    try:
        from rapidocr_onnxruntime import RapidOCR  # type: ignore

        return RapidOCR()
    except Exception:
        try:
            from rapidocr import RapidOCR  # type: ignore

            return RapidOCR()
        except Exception:
            return None


def _ocr_pdf(raw: bytes) -> Tuple[str, str]:
    """Render scanned/outlined PDF pages and OCR them when RapidOCR + PyMuPDF exist."""
    if not ocr_enabled():
        return "", "ocr disabled"
    mod = _pymupdf_mod()
    if mod is None:
        return "", "ocr skipped (install pymupdf)"
    engine = _ocr_engine()
    if engine is None:
        return "", "ocr skipped (install rapidocr-onnxruntime)"
    try:
        doc = mod.open(stream=raw, filetype="pdf")
    except Exception as exc:
        return "", f"ocr open failed: {exc}"
    pages: List[str] = []
    max_pages = min(pdf_max_pages(), 80)
    try:
        for i, page in enumerate(doc):
            if i >= max_pages:
                break
            try:
                pix = page.get_pixmap(matrix=mod.Matrix(2, 2), alpha=False)
                img = pix.tobytes("png")
            except Exception:
                continue
            try:
                result = engine(img)
            except Exception:
                continue
            lines = _ocr_lines(result)
            if lines:
                pages.append("\n".join(lines))
    finally:
        try:
            doc.close()
        except Exception:
            pass
    text = "\n\n".join(p.strip() for p in pages if p.strip())
    if not text.strip():
        return "", "ocr produced no text"
    return text, "extracted via ocr"


def _ocr_lines(result: object) -> List[str]:
    rows = result
    if isinstance(result, tuple) and result:
        rows = result[0]
    if not isinstance(rows, list):
        return []
    lines: List[str] = []
    for item in rows:
        text = ""
        if isinstance(item, dict):
            text = str(item.get("text") or item.get("txt") or "")
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            maybe = item[1]
            if isinstance(maybe, (list, tuple)) and maybe:
                text = str(maybe[0])
            else:
                text = str(maybe or "")
        if text.strip():
            lines.append(text.strip())
    return lines


def _crude_chunk_is_text(inner: str) -> bool:
    """Keep literal PDF strings that look like language, not compressed bytes."""
    if len(inner.strip()) < 2:
        return False
    n = len(inner)
    if sum(1 for ch in inner if ord(ch) < 32 and ch not in "\n\t") > n // 4:
        return False
    good = 0
    for ch in inner:
        if ch.isalnum() or ch.isspace() or _is_cjk_char(ch):
            good += 1
        elif ch in ".,;:!?-_/'\"()[]{}<>+=@#%&*$":
            good += 1
    return good / n >= 0.55


def _crude_pdf_text(raw: bytes) -> Tuple[str, str]:
    """Pull readable Latin/CJK strings from PDF literal strings — lossy but dep-free."""
    try:
        decoded = raw.decode("latin-1", errors="ignore")
    except Exception:
        return "", "could not decode PDF bytes"
    # BT ... Tj / TJ text operators — grab parenthesized strings
    chunks = re.findall(r"\((?:\\.|[^\\()]){2,200}\)", decoded)
    out: list[str] = []
    for ch in chunks:
        inner = ch[1:-1]
        inner = (
            inner.replace("\\n", "\n")
            .replace("\\r", "")
            .replace("\\t", "\t")
            .replace("\\(", "(")
            .replace("\\)", ")")
            .replace("\\\\", "\\")
        )
        # Drop binary / CID-stream noise (high-bit latin-1 is not CJK)
        if not _crude_chunk_is_text(inner):
            continue
        out.append(inner)
    text = " ".join(out)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip(), "crude PDF text (lossy)"


def _xml_texts(xml: str) -> str:
    parts = re.findall(r">([^<]{1,4000})<", xml)
    return "\n".join(p.strip() for p in parts if p.strip())


def _extract_office(raw: bytes, suffix: str) -> Tuple[str, str]:
    """Dep-free OOXML scrape (docx/xlsx/pptx). Not a WeKnora anydoc clone."""
    import io
    import zipfile

    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except Exception as exc:
        return "", f"not a zip OOXML ({exc})"
    names = zf.namelist()
    chunks: List[str] = []
    if suffix == ".docx":
        targets = [n for n in names if n.startswith("word/") and n.endswith(".xml")]
    elif suffix == ".xlsx":
        targets = [
            n
            for n in names
            if n.startswith("xl/") and n.endswith(".xml") and ("sharedStrings" in n or "/worksheets/" in n)
        ]
    else:
        targets = [n for n in names if n.startswith("ppt/slides/slide") and n.endswith(".xml")]
    for name in targets[:80]:
        try:
            xml = zf.read(name).decode("utf-8", errors="replace")
        except Exception:
            continue
        text = _xml_texts(xml)
        if text:
            chunks.append(text)
    body = "\n\n".join(chunks).strip()
    if not body:
        return "", f"{suffix} had no text nodes"
    return body, f"extracted via OOXML ({suffix})"


def default_tags_for_path(path: Path) -> str:
    suf = path.suffix.lower()
    if suf in {".md", ".markdown", ".mdx"}:
        return "file,markdown"
    if suf in HTML_SUFFIXES:
        return "file,html"
    if suf == ".pdf":
        return "file,pdf"
    if suf in OFFICE_SUFFIXES:
        return f"file,office,{suf.lstrip('.')}"
    if suf in IMAGE_SUFFIXES:
        return "file,image"
    if suf in {".txt", ".rst", ".org"}:
        return "file,text"
    return "file"


def default_tags_for_name(filename: str) -> str:
    return default_tags_for_path(Path(filename or "upload.txt"))
