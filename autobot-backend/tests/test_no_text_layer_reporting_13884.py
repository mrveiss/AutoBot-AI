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

Fixtures are real image-only PDFs, not mocks. Mocking ``PdfReader`` to return
empty pages would prove the branch runs without proving that a genuine scan
reaches it — and a scanned PDF differs from an empty one in ways only a real
file exercises.
"""

import io

import pytest

from media.core.types import MediaInput, MediaType, ProcessingIntent
from media.document.extraction import (
    DEFAULT_MIN_TEXT_PAGE_RATIO,
    ExtractedDocument,
    PageText,
    extract_pdf,
    min_text_page_ratio,
)
from media.document.pipeline import DocumentPipeline


def _pdf(pages: list) -> bytes:
    """Build a real PDF. ``None`` draws an image (a scanned page); str draws text."""
    pytest.importorskip("reportlab", reason="reportlab needed to synthesize PDF fixtures")
    pytest.importorskip("PIL", reason="Pillow needed to synthesize image-only pages")
    from PIL import Image
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    for entry in pages:
        if entry is None:
            pdf.drawImage(ImageReader(Image.new("RGB", (600, 800), "white")), 0, 0, width=400, height=500)
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
    """Consumers need a field to branch on, not a heuristic over empty strings."""
    scanned = _result(_pdf([None]))
    blank_text_file = DocumentPipeline()._to_result(ExtractedDocument(format="text", text=""), {})

    assert scanned["processing_status"] == "no_text_layer"
    assert blank_text_file.get("processing_status") == "no_text_layer"
    # ...and a genuinely readable document carries no such marker at all.
    assert "processing_status" not in _result(_pdf(["real content"]))


def test_born_digital_pdf_still_extracts_unchanged():
    """Regression guard: the common case must not pay for the scanned case."""
    data = _result(_pdf(["first page", "second page"]))

    assert data["confidence"] == 0.95
    assert "processing_status" not in data
    assert "empty_pages" not in data
    assert "first page" in data["extracted_text"]


# ---------------------------------------------------------------------------
# Page-level reporting — you can only OCR what you know is missing
# ---------------------------------------------------------------------------


def test_mixed_pdf_reports_which_pages_were_unreadable():
    data = _result(_pdf(["a", "b", "c", None]))

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
# Threshold resolution
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

    raw = _pdf(["a", None])  # exactly 0.5

    monkeypatch.setattr(config.misc, "document_min_text_page_ratio", "0.4", raising=False)
    assert "processing_status" not in _result(raw)

    monkeypatch.setattr(config.misc, "document_min_text_page_ratio", "0.6", raising=False)
    assert _result(raw)["processing_status"] == "no_text_layer"


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
