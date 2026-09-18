"""File → text helpers for KB ingest (md/txt/rst + optional PDF, no hard deps)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional, Tuple

TEXT_SUFFIXES = {".md", ".markdown", ".txt", ".rst", ".org", ".mdx"}
PDF_SUFFIXES = {".pdf"}
OFFICE_SUFFIXES = {".docx", ".xlsx", ".pptx"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
SUPPORTED_SUFFIXES = TEXT_SUFFIXES | PDF_SUFFIXES | OFFICE_SUFFIXES | IMAGE_SUFFIXES
MAX_INGEST_BYTES = 512_000


def is_ingestible(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_SUFFIXES


def read_file_as_text(
    path: Path, *, max_bytes: int = MAX_INGEST_BYTES
) -> Tuple[str, str]:
    """Return (text, note). note is empty on success; non-empty explains degrade."""
    raw = path.read_bytes()
    return read_bytes_as_text(raw, path.suffix, filename=path.name, max_bytes=max_bytes)


def read_bytes_as_text(
    raw: bytes,
    suffix: str,
    *,
    filename: str = "",
    max_bytes: int = MAX_INGEST_BYTES,
) -> Tuple[str, str]:
    """Same extractors as ``read_file_as_text`` but from in-memory bytes."""
    if len(raw) > max_bytes:
        raise ValueError(f"file too large ({len(raw)} bytes, max {max_bytes})")
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
    if suffix in PDF_SUFFIXES:
        text, note = _extract_pdf(raw)
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


def _extract_pdf(raw: bytes) -> Tuple[str, str]:
    """Best-effort PDF text. Prefer pypdf if installed; else crude stream scrape."""
    try:
        from pypdf import PdfReader  # type: ignore
        import io

        reader = PdfReader(io.BytesIO(raw))
        parts = []
        for page in reader.pages[:80]:
            try:
                parts.append(page.extract_text() or "")
            except Exception:
                continue
        text = "\n\n".join(p.strip() for p in parts if p and p.strip())
        if text.strip():
            return text, "extracted via pypdf"
    except ImportError:
        pass
    except Exception as exc:
        # Fall through to crude extractor
        crude, _ = _crude_pdf_text(raw)
        if crude.strip():
            return crude, f"pypdf failed ({exc}); used crude extractor"
        return "", f"pypdf failed: {exc}"

    crude, note = _crude_pdf_text(raw)
    if crude.strip():
        return crude, note or "extracted via crude PDF parser"
    return "", "PDF text extraction unavailable (install pypdf for better results)"


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
        # Drop binary noise
        if sum(1 for c in inner if ord(c) < 32 and c not in "\n\t") > len(inner) // 4:
            continue
        if len(inner.strip()) >= 2:
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
