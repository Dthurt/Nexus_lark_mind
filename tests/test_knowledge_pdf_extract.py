"""PDF ingest: reject mojibake/crude binary; fall back pypdf → pymupdf → OCR."""

from __future__ import annotations

import pytest

from src.core_kernel.plugin_runtime import knowledge_ingest as ki


def test_pdf_text_is_garbled_heuristics():
    chinese = "从VPN到aTrust，开启办公安全新纪元。深信服办公安全。" * 3
    assert ki._pdf_text_is_garbled(chinese) is False
    assert ki._pdf_text_is_garbled("HelloPDFWorld and more latin words here") is False

    cid = "(cid:11)(cid:12)(cid:13)(cid:14) leftover"
    assert ki._pdf_text_is_garbled(cid) is True

    repl = "\ufffd" * 20 + "abcde"
    assert ki._pdf_text_is_garbled(repl) is True

    moji = "ä¸­æ–‡æµ‹è¯•ä¸­æ–‡" * 4
    assert ki._pdf_text_is_garbled(moji, hint="中文标题.pdf") is True

    binary = "ÿ\x96:\x10¢Mm\x93Ùx\x8cýì" * 8
    assert ki._pdf_text_is_garbled(binary, hint="从VPN到aTrust.pdf") is True

    english = (
        "Quarterly VPN and office security report. "
        "This document describes aTrust rollout and architecture."
    )
    assert ki._pdf_text_is_garbled(english, hint="从VPN到aTrust.pdf") is False


def test_garbled_pypdf_falls_back_to_pymupdf(monkeypatch):
    monkeypatch.setenv("KB_OCR", "0")
    monkeypatch.setattr(
        ki, "_pypdf_extract", lambda _raw: ("(cid:11)(cid:12)(cid:13)(cid:20)", "extracted via pypdf")
    )
    monkeypatch.setattr(
        ki,
        "_pymupdf_extract",
        lambda _raw: ("从VPN到aTrust，开启办公安全新纪元", "extracted via pymupdf"),
    )
    monkeypatch.setattr(ki, "_crude_pdf_text", lambda _raw: ("", "crude empty"))
    monkeypatch.setattr(ki, "_ocr_pdf", lambda _raw: ("", "ocr disabled"))

    text, note = ki.read_bytes_as_text(b"%PDF-1.4 fake", ".pdf", filename="从VPN到aTrust.pdf")
    assert "办公安全" in text
    assert "pymupdf" in note


def test_empty_pypdf_falls_back_to_pymupdf(monkeypatch):
    monkeypatch.setenv("KB_OCR", "0")
    monkeypatch.setattr(ki, "_pypdf_extract", lambda _raw: ("", "pypdf produced no text"))
    monkeypatch.setattr(
        ki,
        "_pymupdf_extract",
        lambda _raw: ("CID font 中文正文 aTrust", "extracted via pymupdf"),
    )
    monkeypatch.setattr(ki, "_crude_pdf_text", lambda _raw: ("", ""))
    monkeypatch.setattr(ki, "_ocr_pdf", lambda _raw: ("", "ocr disabled"))

    text, note = ki.read_bytes_as_text(b"%PDF-1.4 fake", ".pdf", filename="手册.pdf")
    assert "中文正文" in text
    assert note == "extracted via pymupdf"


def test_garbled_crude_falls_back_to_ocr(monkeypatch):
    monkeypatch.setenv("KB_OCR", "1")
    monkeypatch.setattr(ki, "_pypdf_extract", lambda _raw: ("", "pypdf produced no text"))
    monkeypatch.setattr(ki, "_pymupdf_extract", lambda _raw: ("", "pymupdf produced no text"))
    monkeypatch.setattr(
        ki,
        "_crude_pdf_text",
        lambda _raw: ("ÿ\x96:\x10¢Mm" * 30, "crude PDF text (lossy)"),
    )
    monkeypatch.setattr(
        ki,
        "_ocr_pdf",
        lambda _raw: ("从VPN到aTrust 办公安全新纪元", "extracted via ocr"),
    )

    text, note = ki.read_bytes_as_text(b"%PDF-1.4 fake", ".pdf", filename="从VPN到aTrust.pdf")
    assert "aTrust" in text
    assert "ocr" in note


def test_garbled_crude_without_ocr_raises(monkeypatch):
    monkeypatch.setenv("KB_OCR", "0")
    monkeypatch.setattr(ki, "_pypdf_extract", lambda _raw: ("", "pypdf produced no text"))
    monkeypatch.setattr(ki, "_pymupdf_extract", lambda _raw: ("", "pymupdf produced no text"))
    monkeypatch.setattr(
        ki,
        "_crude_pdf_text",
        lambda _raw: ("ÿ\x96:\x10¢Mm" * 30, "crude PDF text (lossy)"),
    )
    monkeypatch.setattr(ki, "_ocr_pdf", lambda _raw: ("", "ocr disabled"))

    with pytest.raises(ValueError, match="no extractable text"):
        ki.read_bytes_as_text(b"%PDF-1.4 fake", ".pdf", filename="从VPN到aTrust.pdf")


def test_crude_latin_pdf_still_ingests():
    raw = b"%PDF-1.4\nBT (HelloPDFWorld) Tj ET\n%%EOF"
    text, note = ki.read_bytes_as_text(raw, ".pdf", filename="tiny.pdf")
    assert "HelloPDFWorld" in text
    assert note
