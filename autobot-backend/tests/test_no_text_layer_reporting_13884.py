# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Text-layer reporting guards (#13884).

An image-only PDF parses cleanly and yields no text. The media pipeline used to
report that as ``success=True`` with ``confidence=0.95`` and an empty
``extracted_text`` — which asserts the document is *blank* rather than *unread*.
A consumer could not tell the two apart, and #13896's OCR fallback has nothing
trustworthy to trigger on while the pipeline's own result says the document was
read successfully.

A page-ratio check alone is also blind to the most common scan shape: a
scanner, DMS, or Bates stamper overlays a page number or "CONFIDENTIAL" on
every page, so every page technically "has text" while carrying nothing
usable. The per-page character floor below is what catches that.

Fixtures are real image-only PDFs, not mocks. Mocking ``PdfReader`` to return
empty pages would prove the branch runs without proving that a genuine scan
reaches it — and a scanned PDF differs from an empty one in ways only a real
file exercises. Text pages use realistic-length prose rather than one-word
placeholders, because the character floor this issue adds would otherwise
flag the *test fixtures* as unusable, not just genuine stamped scans.
"""

import io

import pytest

from media.core.types import MediaInput, MediaType, ProcessingIntent
from media.document.extraction import (
    DEFAULT_MIN_CHARS_PER_PAGE,
    DEFAULT_MIN_TEXT_PAGE_RATIO,
    ExtractedDocument,
    PageText,
    extract_pdf,
    min_chars_per_page,
    min_text_page_ratio,
)
from media.document.pipeline import DocumentPipeline

# Realistic-length prose so a text page clears the #13884 per-page character
# floor by construction — genuine content, not a one-word placeholder that
# would (correctly) be flagged the same way a stamp would.
_REAL_PAGE_TEXT = (
    "This page carries a full paragraph of ordinary prose, long enough to "
    "clear the per-page character floor with room to spare."
)


def _pdf(pages: list) -> bytes:
    """Build a real PDF.

    An entry is one of:
      - ``None``            — a scanned page: image only, no text at all.
      - ``str``              — a born-digital page carrying that text.
      - ``("stamp", text)``  — a scanned page carrying a short stamp (a page
        number, Bates number, or filename) on top of the image, the shape a
        real stamped scan takes.
    """
    pytest.importorskip("reportlab", reason="reportlab needed to synthesize PDF fixtures")
    pytest.importorskip("PIL", reason="Pillow needed to synthesize image-only pages")
    from PIL import Image
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    blank_page = ImageReader(Image.new("RGB", (600, 800), "white"))
    for entry in pages:
        if entry is None:
            pdf.drawImage(blank_page, 0, 0, width=400, height=500)
        elif isinstance(entry, tuple) and entry[0] == "stamp":
            pdf.drawImage(blank_page, 0, 0, width=400, height=500)
            pdf.setFont("Helvetica", 9)
            pdf.drawString(400, 20, entry[1])
        else:
            pdf.drawString(72, 720, entry)
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def _result(raw: bytes) -> dict:
    media_input = MediaInput(
        media_id="doc",
        media_type=MediaType.DOCUMENT,
        intent=ProcessingIntent.ANALYSIS,
        data=raw,
        mime_type="application/pdf",
        metadata={},
    )
    import asyncio

    return asyncio.run(DocumentPipeline()._process_impl(media_input)).result_data


# ---------------------------------------------------------------------------
# The reported defect
# ---------------------------------------------------------------------------


def test_image_only_pdf_is_not_reported_as_confident_success():
    """The regression this issue exists for: 0.95 on a zero-text extraction."""
    data = _result(_pdf([None]))

    assert data["extracted_text"].strip() == ""
    assert data["confidence"] == 0.0, "an unread document must not score like a read one"
    assert data["processing_status"] == "no_text_layer"
    assert "OCR" in data["text_layer_reason"]


def test_unread_document_is_distinguishable_from_a_blank_one():
    """Consumers need a field to branch on, not a heuristic over empty strings.

    A scanned PDF (paginated, nothing recoverable) and a blank text file
    (unpaginated, nothing recoverable) fail for different reasons and get
    different statuses — the whole premise of this issue.
    """
    scanned = _result(_pdf([None]))
    blank_text_file = DocumentPipeline()._to_result(ExtractedDocument(format="text", text=""), {})

    assert scanned["processing_status"] == "no_text_layer"
    assert blank_text_file["processing_status"] == "empty_document"
    assert scanned["processing_status"] != blank_text_file["processing_status"]
    assert "OCR" not in blank_text_file["text_layer_reason"], "a blank text file does not need OCR"
    # ...and a genuinely readable document carries no such marker at all.
    assert "processing_status" not in _result(_pdf([_REAL_PAGE_TEXT]))


def test_born_digital_pdf_still_extracts_unchanged():
    """Regression guard: the common case must not pay for the scanned case."""
    data = _result(_pdf([f"first page: {_REAL_PAGE_TEXT}", f"second page: {_REAL_PAGE_TEXT}"]))

    assert data["confidence"] == 0.95
    assert "processing_status" not in data
    assert "empty_pages" not in data
    assert "first page" in data["extracted_text"]


# ---------------------------------------------------------------------------
# Finding 1 — a page-number/Bates stamp on every page must not read as usable
# ---------------------------------------------------------------------------


def test_stamped_scan_is_not_reported_as_usable_despite_nonzero_chars():
    """Every page "has text" (ratio 1.0), but it is only a page-number stamp."""
    pages = [("stamp", f"Page {i} of 10") for i in range(1, 11)]
    data = _result(_pdf(pages))

    assert data["text_page_ratio"] == 1.0
    assert data["extracted_text"].strip() != "", "the stamp text itself is non-empty"
    assert data["confidence"] == 0.0, "a stamp-only scan must not score like a read document"
    assert data["processing_status"] == "no_text_layer"
    assert "OCR" in data["text_layer_reason"]
    assert data["chars_per_page"] < DEFAULT_MIN_CHARS_PER_PAGE


def test_chars_per_page_floor_does_not_reject_a_genuine_short_page():
    """A short but real page (an invoice-style cover page) must still pass."""
    invoice_page = "Invoice #12345. Date: 2026-01-01. Bill To: Acme Corp. Total Due: $160.00."
    data = _result(_pdf([invoice_page]))

    assert "processing_status" not in data
    assert data["confidence"] == 0.95


def test_avg_chars_per_page_uses_raw_page_text_not_rendered_markers():
    """The floor must not be inflated by our own ``## Page N`` marker overhead."""
    doc = ExtractedDocument(
        format="pdf",
        text="ignored — avg_chars_per_page reads .pages, not .text",
        pages=(PageText(1, "abc"), PageText(2, "de")),
        page_count=2,
    )
    assert doc.avg_chars_per_page == 2.5


# ---------------------------------------------------------------------------
# Page-level reporting — you can only OCR what you know is missing
# ---------------------------------------------------------------------------


def test_mixed_pdf_reports_which_pages_were_unreadable():
    pages = [f"page a: {_REAL_PAGE_TEXT}", f"page b: {_REAL_PAGE_TEXT}", f"page c: {_REAL_PAGE_TEXT}", None]
    data = _result(_pdf(pages))

    assert data["empty_pages"] == [4]
    assert data["text_page_ratio"] == 0.75
    # Mostly readable, so it is still a usable extraction.
    assert data["confidence"] == 0.95
    assert "processing_status" not in data


def test_mostly_scanned_pdf_is_unusable_even_though_it_has_some_text():
    """`has_text` is True here and misleading; the ratio is what decides."""
    data = _result(_pdf([None, None, None, "stray text"]))

    assert data["empty_pages"] == [1, 2, 3]
    assert data["text_page_ratio"] == 0.25
    assert data["processing_status"] == "no_text_layer"
    assert data["confidence"] == 0.0


def test_page_numbers_reported_are_one_indexed():
    """Off-by-one here sends OCR at the wrong page."""
    data = _result(_pdf([None, "readable"]))
    assert data["empty_pages"] == [1]


# ---------------------------------------------------------------------------
# Threshold resolution — page ratio
# ---------------------------------------------------------------------------


def test_threshold_is_configurable_not_a_literal(monkeypatch):
    """AC: sourced from an env var, with the default applied when unset."""
    from autobot_shared.ssot_config import config

    monkeypatch.setattr(config.misc, "document_min_text_page_ratio", "", raising=False)
    assert min_text_page_ratio() == DEFAULT_MIN_TEXT_PAGE_RATIO

    monkeypatch.setattr(config.misc, "document_min_text_page_ratio", "0.9", raising=False)
    assert min_text_page_ratio() == 0.9


@pytest.mark.parametrize("bad", ["not-a-number", "-0.5", "1.5"])
def test_invalid_threshold_falls_back_to_the_default(monkeypatch, bad):
    """A misconfigured knob must not silently disable the check."""
    from autobot_shared.ssot_config import config

    monkeypatch.setattr(config.misc, "document_min_text_page_ratio", bad, raising=False)
    assert min_text_page_ratio() == DEFAULT_MIN_TEXT_PAGE_RATIO


def test_threshold_actually_changes_the_verdict(monkeypatch):
    """Guards against a knob that is read and then ignored."""
    from autobot_shared.ssot_config import config

    raw = _pdf([_REAL_PAGE_TEXT * 2, None])  # exactly 0.5 ratio, well above the chars floor

    monkeypatch.setattr(config.misc, "document_min_text_page_ratio", "0.4", raising=False)
    assert "processing_status" not in _result(raw)

    monkeypatch.setattr(config.misc, "document_min_text_page_ratio", "0.6", raising=False)
    assert _result(raw)["processing_status"] == "no_text_layer"


# ---------------------------------------------------------------------------
# Threshold resolution — characters per page (#13884 finding 1)
# ---------------------------------------------------------------------------


def test_chars_floor_is_configurable_not_a_literal(monkeypatch):
    from autobot_shared.ssot_config import config

    monkeypatch.setattr(config.misc, "document_min_chars_per_page", "", raising=False)
    assert min_chars_per_page() == DEFAULT_MIN_CHARS_PER_PAGE

    monkeypatch.setattr(config.misc, "document_min_chars_per_page", "10", raising=False)
    assert min_chars_per_page() == 10.0


@pytest.mark.parametrize("bad", ["not-a-number", "-5"])
def test_invalid_chars_floor_falls_back_to_the_default(monkeypatch, bad):
    """A misconfigured knob must not silently disable the check."""
    from autobot_shared.ssot_config import config

    monkeypatch.setattr(config.misc, "document_min_chars_per_page", bad, raising=False)
    assert min_chars_per_page() == DEFAULT_MIN_CHARS_PER_PAGE


def test_chars_floor_actually_changes_the_verdict(monkeypatch):
    """Guards against a knob that is read and then ignored."""
    from autobot_shared.ssot_config import config

    raw = _pdf([("stamp", "Page 1 of 2"), ("stamp", "Page 2 of 2")])  # ~12 chars/page, ratio 1.0

    monkeypatch.setattr(config.misc, "document_min_chars_per_page", "5", raising=False)
    assert "processing_status" not in _result(raw)

    monkeypatch.setattr(config.misc, "document_min_chars_per_page", "20", raising=False)
    assert _result(raw)["processing_status"] == "no_text_layer"


# ---------------------------------------------------------------------------
# Finding 3 — blank / table-only documents are not "scanned, needs OCR"
# ---------------------------------------------------------------------------


def test_blank_text_file_reports_empty_document_not_no_text_layer():
    """A blank ``.txt`` is empty, not unread — OCR cannot fix it either way."""
    result = DocumentPipeline()._to_result(ExtractedDocument(format="text", text=""), {})

    assert result["processing_status"] == "empty_document"
    assert result["confidence"] == 0.0
    assert "OCR" not in result["text_layer_reason"]


def test_table_only_docx_is_a_successful_extraction_not_no_text_layer():
    """A DOCX whose content is entirely a table is read fine — the data is in ``tables``."""
    doc = ExtractedDocument(
        format="docx",
        text="",
        tables=([["Item", "Price"], ["Widget", "42"]],),
    )
    result = DocumentPipeline()._to_result(doc, {})

    assert "processing_status" not in result
    assert result["confidence"] == 0.95
    assert result["tables"] == [[["Item", "Price"], ["Widget", "42"]]]


def test_has_usable_content_reflects_tables_even_without_text():
    doc = ExtractedDocument(format="docx", text="", tables=([["a"]],))
    assert doc.has_usable_text_layer is False
    assert doc.has_usable_content is True


# ---------------------------------------------------------------------------
# Core properties
# ---------------------------------------------------------------------------


def test_unpaginated_formats_are_judged_on_content_alone():
    """A DOCX has no pages; the ratio must not divide by zero or report 0.0."""
    assert ExtractedDocument(format="docx", text="content").text_page_ratio == 1.0
    assert ExtractedDocument(format="docx", text="   ").text_page_ratio == 0.0


def test_empty_page_numbers_skips_whitespace_only_pages():
    doc = ExtractedDocument(
        format="pdf",
        text="x",
        pages=(PageText(1, "real"), PageText(2, "  \n "), PageText(3, "")),
        page_count=3,
    )
    assert doc.empty_page_numbers == (2, 3)


def test_extract_pdf_keeps_unreadable_pages_in_the_page_list():
    """Dropping them would make page_count lie and hide what needs OCR."""
    extracted = extract_pdf(_pdf(["a", None, "c"]))
    assert extracted.page_count == 3
    assert extracted.empty_page_numbers == (2,)
