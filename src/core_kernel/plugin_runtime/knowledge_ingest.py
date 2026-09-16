"""File → text helpers for KB ingest (md/txt/rst + optional PDF, no hard deps)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional, Tuple

TEXT_SUFFIXES = {".md", ".markdown", ".txt", ".rst", ".org", ".mdx"}
PDF_SUFFIXES = {".pdf"}
SUPPORTED_SUFFIXES = TEXT_SUFFIXES | PDF_SUFFIXES


def is_ingestible(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_SUFFIXES


def read_file_as_text(
    path: Path, *, max_bytes: int = 512_000
) -> Tuple[str, str]:
    """Return (text, note). note is empty on success; non-empty explains degrade."""
    raw = path.read_bytes()
    if len(raw) > max_bytes:
        raise ValueError(f"file too large ({len(raw)} bytes, max {max_bytes})")
    suffix = path.suffix.lower()
    if suffix in PDF_SUFFIXES:
        text, note = _extract_pdf(raw)
        if not text.strip():
            raise ValueError(note or "PDF produced no extractable text")
        return text, note
    # Plain / markdown family
    text = raw.decode("utf-8", errors="replace")
    # Strip UTF-8 BOM
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


def default_tags_for_path(path: Path) -> str:
    suf = path.suffix.lower()
    if suf in {".md", ".markdown", ".mdx"}:
        return "file,markdown"
    if suf == ".pdf":
        return "file,pdf"
    if suf in {".txt", ".rst", ".org"}:
        return "file,text"
    return "file"
