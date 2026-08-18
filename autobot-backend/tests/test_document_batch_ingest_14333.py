# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Batch-ingest wire-in guards (#14333).

`utils/document_parser.py` and `utils/document_extractors.py` delegated correctly
after #13893 but had **zero callers** — 728 lines reachable from nothing. They are
now the extraction path for directory ingest.

Wiring them in exposed two live defects in `knowledge/documents.py`, and those are
what most of these tests pin:

- `add_document_from_file` advertised PDF support in its docstring and called
  ``read_text(encoding="utf-8")``, so a PDF either raised on its binary header or
  was stored as mojibake.
- `add_documents_from_directory` defaulted to ``pattern="*.txt"``, so a directory
  of PDFs ingested nothing and returned ``total_files: 0`` — a successful-looking
  no-op.
"""

import io

import pytest

from utils.document_extractors import DocumentExtractor


def _pdf_bytes(pages: list) -> bytes:
    pytest.importorskip("reportlab", reason="reportlab needed to synthesize PDF fixtures")
    from reportlab.pdfgen import canvas

    filler = " Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor."
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    for text in pages:
        pdf.drawString(72, 720, text)
        pdf.drawString(72, 700, filler)
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# The extractor is reachable and covers what it claims
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_from_file_reads_a_pdf(tmp_path):
    path = tmp_path / "report.pdf"
    path.write_bytes(_pdf_bytes(["quarterly numbers"]))

    text = await DocumentExtractor.extract_from_file(path)
    assert "quarterly numbers" in text


@pytest.mark.asyncio
async def test_extract_from_file_reads_plain_text(tmp_path):
    path = tmp_path / "notes.md"
    path.write_text("# heading\n\nbody text", encoding="utf-8")

    assert "body text" in await DocumentExtractor.extract_from_file(path)


@pytest.mark.asyncio
async def test_unsupported_format_raises_rather_than_returning_garbage(tmp_path):
    path = tmp_path / "image.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n")

    with pytest.raises(ValueError, match="Unsupported file type"):
        await DocumentExtractor.extract_from_file(path)


def test_discovery_and_extraction_agree_on_the_supported_set():
    """A format listed for discovery but unhandled is a silently smaller ingest."""
    for suffix in DocumentExtractor.get_supported_extensions():
        assert DocumentExtractor.is_supported_format(f"probe{suffix}"), suffix


def test_the_office_formats_are_declared():
    """The breadth document_parser uniquely carries must be discoverable."""
    extensions = set(DocumentExtractor.get_supported_extensions())
    assert {".xlsx", ".pptx", ".odt", ".ods", ".odp", ".odg"} <= extensions


@pytest.mark.asyncio
async def test_office_delegation_reaches_document_parser(tmp_path, monkeypatch):
    """The wire-in itself: the orphaned parser is now on a live path."""
    calls = []

    async def _fake_extract(path, mime_type=None):
        calls.append(path)
        return "sheet contents", {"extraction_success": True}

    from utils import document_parser as parser_module

    monkeypatch.setattr(parser_module.document_parser, "extract_text", _fake_extract)

    path = tmp_path / "book.xlsx"
    path.write_bytes(b"PK\x03\x04stub")

    assert await DocumentExtractor.extract_from_file(path) == "sheet contents"
    assert calls, "DocumentParser was not reached"


@pytest.mark.asyncio
async def test_a_failed_office_parse_raises_rather_than_storing_empty(tmp_path, monkeypatch):
    async def _fake_extract(path, mime_type=None):
        return "", {"extraction_success": False, "extraction_error": "corrupt"}

    from utils import document_parser as parser_module

    monkeypatch.setattr(parser_module.document_parser, "extract_text", _fake_extract)

    path = tmp_path / "broken.odt"
    path.write_bytes(b"stub")

    with pytest.raises(ValueError, match="corrupt"):
        await DocumentExtractor.extract_from_file(path)


# ---------------------------------------------------------------------------
# Directory discovery — the *.txt default was a successful-looking no-op
# ---------------------------------------------------------------------------


def _mixed_directory(tmp_path):
    (tmp_path / "a.pdf").write_bytes(_pdf_bytes(["pdf body"]))
    (tmp_path / "b.txt").write_text("text body", encoding="utf-8")
    (tmp_path / "c.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (tmp_path / "sub").mkdir()
    return tmp_path


@pytest.mark.asyncio
async def test_discovery_without_a_pattern_finds_every_supported_format(tmp_path):
    from knowledge.documents import DocumentsMixin

    found = await DocumentsMixin._discover_documents(DocumentsMixin(), _mixed_directory(tmp_path), None)
    names = {p.name for p in found}

    assert "a.pdf" in names, "the *.txt default is exactly what made this ingest nothing"
    assert "b.txt" in names
    assert "c.png" not in names, "unsupported formats must not be attempted"
    assert "sub" not in names, "directories are not documents"


@pytest.mark.asyncio
async def test_an_explicit_pattern_still_narrows(tmp_path):
    from knowledge.documents import DocumentsMixin

    found = await DocumentsMixin._discover_documents(DocumentsMixin(), _mixed_directory(tmp_path), "*.txt")
    assert {p.name for p in found} == {"b.txt"}
