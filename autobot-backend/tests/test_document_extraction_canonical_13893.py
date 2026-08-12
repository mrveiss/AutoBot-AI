# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Canonical document-extraction guards (#13893).

Five independent PDF extractors existed before the consolidation — three live,
two orphaned — and they disagreed on page markers. One ran the unmaintained
``PyPDF2`` while the repo pinned ``pypdf`` as a security update, so Drive and
OneDrive ingestion used the library everything else had deliberately moved off.

These tests hold the consolidation in place. The structural guards (one reader,
no ``PyPDF2``) are what stop the forks growing back; the behavioural ones run
against real generated PDFs rather than mocked readers, because a mocked
``PdfReader`` would have passed happily against all five old implementations and
proved nothing about which one ran.
"""

import io
import pathlib
import re

import pytest

from media.document.extraction import (
    PAGE_MARKER_TEMPLATE,
    DocumentExtractionError,
    ExtractedDocument,
    PageText,
    detect_format,
    extract_document,
    extract_pdf,
    extract_plain_text,
    render_pages,
    strip_page_markers,
)

_BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[1]
_REQUIREMENTS = _BACKEND_ROOT / "requirements.txt"

# Call sites that must not carry their own PDF reader any more.
_CONSOLIDATED_SOURCES = (
    "api/knowledge.py",
    "media/document/pipeline.py",
    "knowledge/connectors/content_extraction.py",
    "utils/document_parser.py",
    "utils/document_extractors.py",
)


def _make_pdf(pages: list[str]) -> bytes:
    """Build a real multi-page PDF carrying a text layer."""
    reportlab = pytest.importorskip("reportlab", reason="reportlab needed to synthesize a PDF fixture")
    from reportlab.pdfgen import canvas  # noqa: F401  (import validated by importorskip)

    buffer = io.BytesIO()
    pdf = reportlab.pdfgen.canvas.Canvas(buffer)
    for text in pages:
        pdf.drawString(72, 720, text)
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Structural guards — these are what stop the fork growing back
# ---------------------------------------------------------------------------


def test_only_the_canonical_module_constructs_a_pdf_reader():
    """Exactly one module may own a PdfReader; five owning one was the bug."""
    owners = []
    for source in _CONSOLIDATED_SOURCES:
        text = (_BACKEND_ROOT / source).read_text(encoding="utf-8")
        if "PdfReader(" in text:
            owners.append(source)
    assert owners == [], (
        f"{owners} construct their own PdfReader again. All PDF reading belongs in "
        "media/document/extraction.py — five forked implementations is what #13893 removed."
    )


def test_pypdf2_is_not_imported_anywhere():
    """The connectors ran PyPDF2 while the repo pinned pypdf as a security update."""
    offenders = []
    for source in _CONSOLIDATED_SOURCES:
        for line in (_BACKEND_ROOT / source).read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith(("import PyPDF2", "from PyPDF2")):
                offenders.append(source)
    assert offenders == [], f"{offenders} import PyPDF2, which is unmaintained (#13893)"


def test_pypdf2_is_not_declared_as_a_dependency():
    """A removed import that stays declared invites the fork back."""
    declared = [
        line
        for line in _REQUIREMENTS.read_text(encoding="utf-8").splitlines()
        if line.strip().lower().startswith("pypdf2")
    ]
    assert declared == [], f"PyPDF2 is still declared in {_REQUIREMENTS}: {declared}"


# ---------------------------------------------------------------------------
# Behavioural guards — real PDFs, not mocked readers
# ---------------------------------------------------------------------------


def test_pdf_pages_are_extracted_with_the_canonical_marker():
    raw = _make_pdf(["First page body", "Second page body"])
    extracted = extract_pdf(raw)

    assert extracted.format == "pdf"
    assert extracted.page_count == 2
    assert [page.number for page in extracted.pages] == [1, 2]
    assert "First page body" in extracted.text
    assert "Second page body" in extracted.text
    assert PAGE_MARKER_TEMPLATE.format(number=1) in extracted.text
    assert PAGE_MARKER_TEMPLATE.format(number=2) in extracted.text


def test_page_numbers_are_one_indexed_to_match_human_page_numbers():
    """Off-by-one here silently mis-cites every fact extracted from a PDF."""
    extracted = extract_pdf(_make_pdf(["only page"]))
    assert extracted.pages[0].number == 1


def test_a_pdf_with_no_text_layer_extracts_empty_rather_than_raising():
    """Scanned PDFs are the #13884/#13896 case: empty is a result, not a failure."""
    raw = _make_pdf([" "])
    extracted = extract_pdf(raw)

    assert extracted.page_count == 1, "page count must stay truthful even with no text"
    assert not extracted.has_text
    assert extracted.text.strip() == ""


def test_page_count_counts_unreadable_pages_too():
    """Dropping empty pages would hide which pages need OCR."""
    extracted = extract_pdf(_make_pdf(["real text", " ", "more text"]))
    assert extracted.page_count == 3
    assert len(extracted.pages) == 3


def test_corrupt_pdf_raises_the_canonical_error():
    with pytest.raises(DocumentExtractionError):
        extract_pdf(b"%PDF-1.4 this is not actually a pdf")


def test_detect_format_prefers_magic_bytes_over_mime_type():
    """A mislabelled upload must be parsed by what it is, not what it claims."""
    assert detect_format(b"%PDF-1.7 ...", "text/plain") == "pdf"
    assert detect_format(b"plain content", "application/pdf") == "pdf"
    assert detect_format(b"plain content", "") == "text"


def test_plain_text_falls_back_to_latin1_on_undecodable_bytes():
    extracted = extract_plain_text(b"caf\xe9")
    assert extracted.format == "text"
    assert extracted.text  # decoded rather than raised


def test_extract_document_dispatches_on_detected_format():
    assert extract_document(_make_pdf(["body"])).format == "pdf"
    assert extract_document(b"just text").format == "text"


# ---------------------------------------------------------------------------
# Rendering / provenance split (the seam #13894 builds on)
# ---------------------------------------------------------------------------


def test_render_pages_skips_pages_with_no_text():
    """A bare marker with nothing under it is noise in the embedding."""
    rendered = render_pages([PageText(1, "kept"), PageText(2, "   "), PageText(3, "also kept")])
    assert PAGE_MARKER_TEMPLATE.format(number=2) not in rendered
    assert "kept" in rendered and "also kept" in rendered


def test_structured_pages_survive_independently_of_the_rendered_text():
    """#13894 needs per-page text that is not recoverable by parsing markers back out."""
    extracted = extract_pdf(_make_pdf(["alpha", "beta"]))
    assert extracted.pages[1].text.strip().startswith("beta")


def test_strip_page_markers_removes_every_marker():
    rendered = render_pages([PageText(1, "alpha"), PageText(2, "beta")])
    stripped = strip_page_markers(rendered)
    assert "alpha" in stripped and "beta" in stripped
    assert not re.search(r"^## Page \d+$", stripped, flags=re.MULTILINE)


def test_has_text_reports_whitespace_only_documents_as_empty():
    assert not ExtractedDocument(format="text", text="   \n\t ").has_text
    assert ExtractedDocument(format="text", text="content").has_text
