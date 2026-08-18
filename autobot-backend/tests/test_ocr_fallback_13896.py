# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""OCR fallback guards (#13896).

#13884 made a scanned PDF *detectable*; this makes it *recoverable*. The tests
split into two groups on purpose:

- Contract tests, which run everywhere. They pin the behaviour that matters when
  the toolchain is absent — degrade with a reason, never raise, never claim an
  attempt that did not happen. This is the half that protects hosts like the ones
  #13885 found, where the binary shipped and the binding did not.
- End-to-end tests, which need ``pytesseract``, ``PyMuPDF`` and a working
  tesseract binary. They ``skip`` where those are missing rather than passing
  vacuously, so a green run in a stripped environment never reads as proof that
  OCR works.

Fixtures are real image-only PDFs with rendered text, not mocks. A mocked
``image_to_string`` would assert the wiring and prove nothing about whether a
scanned page can actually be read.
"""

import io

import pytest

from media.core.types import MediaInput, MediaType, ProcessingIntent
from media.document.extraction import extract_pdf
from media.document.ocr import (
    DEFAULT_MAX_OCR_PAGES,
    DEFAULT_OCR_DPI,
    OcrResult,
    OcrUnavailableError,
    max_ocr_pages,
    ocr_availability,
    ocr_dpi,
    ocr_enabled,
    ocr_environment_report,
    ocr_pdf_pages,
    require_ocr,
)
from media.document.pipeline import DocumentPipeline

_OCR_AVAILABLE, _OCR_REASON = ocr_availability()
needs_ocr = pytest.mark.skipif(not _OCR_AVAILABLE, reason=f"OCR toolchain unavailable: {_OCR_REASON}")


def _scanned_pdf(texts: list) -> bytes:
    """A PDF whose pages are images of text — no text layer at all.

    ``None`` renders a blank page; a string is drawn into the image so OCR has
    something real to read.
    """
    pytest.importorskip("reportlab", reason="reportlab needed to synthesize PDF fixtures")
    pytest.importorskip("PIL", reason="Pillow needed to render image-only pages")
    from PIL import Image, ImageDraw
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    for text in texts:
        image = Image.new("RGB", (1200, 1600), "white")
        if text:
            draw = ImageDraw.Draw(image)
            # Large and repeated: OCR on a synthetic bitmap with the default font
            # is unreliable at small sizes, and this is testing the pipeline, not
            # tesseract's accuracy floor.
            for row in range(6):
                draw.text((60, 80 + row * 120), text, fill="black")
        pdf.drawImage(ImageReader(image), 0, 0, width=600, height=800)
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def _born_digital_pdf(pages: list) -> bytes:
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


def _result(raw: bytes) -> dict:
    import asyncio

    media_input = MediaInput(
        media_id="doc",
        media_type=MediaType.DOCUMENT,
        intent=ProcessingIntent.ANALYSIS,
        data=raw,
        mime_type="application/pdf",
        metadata={},
    )
    return asyncio.run(DocumentPipeline()._process_impl(media_input)).result_data


# ---------------------------------------------------------------------------
# Contract — holds with or without the toolchain
# ---------------------------------------------------------------------------


def test_requesting_no_pages_is_not_an_attempt():
    result = ocr_pdf_pages(b"%PDF-1.4", [])
    assert result.attempted is False
    assert result.pages == {}


def test_a_missing_toolchain_degrades_with_a_reason_rather_than_raising():
    """The #13885 shape: the binary ships, the binding does not, nothing alerts."""
    result = ocr_pdf_pages(b"not a real pdf", [1])
    assert isinstance(result, OcrResult)
    if not _OCR_AVAILABLE:
        assert result.attempted is False
        assert result.reason, "a skipped attempt must say why"
        assert result.skipped_pages == (1,)


def test_disabled_by_config_reports_that_rather_than_unavailability(monkeypatch):
    from autobot_shared.ssot_config import config

    monkeypatch.setattr(config.misc, "document_ocr_enabled", "false", raising=False)
    result = ocr_pdf_pages(b"%PDF-1.4", [1, 2])

    assert result.attempted is False
    assert "disabled" in result.reason
    assert result.skipped_pages == (1, 2)


def test_ocr_enabled_defaults_on_and_accepts_falsey_spellings(monkeypatch):
    from autobot_shared.ssot_config import config

    monkeypatch.setattr(config.misc, "document_ocr_enabled", "", raising=False)
    assert ocr_enabled() is True
    for value in ("0", "false", "FALSE", "no", "off"):
        monkeypatch.setattr(config.misc, "document_ocr_enabled", value, raising=False)
        assert ocr_enabled() is False, value


@pytest.mark.parametrize("bad", ["not-a-number", "0", "-5"])
def test_invalid_knobs_fall_back_to_defaults(monkeypatch, bad):
    """A misconfigured value must not silently disable the ceiling."""
    from autobot_shared.ssot_config import config

    monkeypatch.setattr(config.misc, "document_ocr_dpi", bad, raising=False)
    monkeypatch.setattr(config.misc, "document_max_ocr_pages", bad, raising=False)
    assert ocr_dpi() == DEFAULT_OCR_DPI
    assert max_ocr_pages() == DEFAULT_MAX_OCR_PAGES


def test_knobs_are_configurable(monkeypatch):
    from autobot_shared.ssot_config import config

    monkeypatch.setattr(config.misc, "document_ocr_dpi", "150", raising=False)
    monkeypatch.setattr(config.misc, "document_max_ocr_pages", "7", raising=False)
    assert ocr_dpi() == 150
    assert max_ocr_pages() == 7


def test_page_ceiling_reports_what_it_skipped(monkeypatch):
    """Silently reading fewer pages than asked is the failure this prevents."""
    from autobot_shared.ssot_config import config

    monkeypatch.setattr(config.misc, "document_max_ocr_pages", "2", raising=False)
    result = ocr_pdf_pages(_scanned_pdf([None, None, None, None]), [1, 2, 3, 4])
    assert result.skipped_pages == (3, 4)


def test_require_ocr_matches_availability():
    if _OCR_AVAILABLE:
        require_ocr()
    else:
        with pytest.raises(OcrUnavailableError):
            require_ocr()


def test_environment_report_answers_the_question_13885_could_not():
    report = ocr_environment_report()
    assert set(report) >= {"available", "reason", "dpi", "max_pages"}
    assert isinstance(report["available"], bool)
    assert report["available"] is _OCR_AVAILABLE


def test_born_digital_documents_never_invoke_ocr(monkeypatch):
    """The cost guard: a readable PDF must not rasterize anything."""
    import media.document.pipeline as pipeline_module

    calls = []
    monkeypatch.setattr(
        "media.document.ocr.ocr_pdf_pages",
        lambda raw, pages: calls.append(pages) or OcrResult(attempted=False),
    )
    assert pipeline_module  # module imported for the patch target to resolve

    data = _result(_born_digital_pdf(["first page", "second page"]))

    assert calls == [], "OCR must not run for a document that already has text"
    assert "ocr_attempted" not in data


# ---------------------------------------------------------------------------
# End to end — needs a real toolchain
# ---------------------------------------------------------------------------


@needs_ocr
def test_a_scanned_pdf_becomes_readable():
    """The capability this issue exists for."""
    raw = _scanned_pdf(["INVOICE"])

    before = extract_pdf(raw)
    assert not before.has_usable_text_layer, "fixture must have no text layer"

    data = _result(raw)
    assert data["ocr_attempted"] is True
    assert "INVOICE" in data["extracted_text"].upper()


@needs_ocr
def test_only_the_unreadable_pages_are_ocred():
    """A mixed document pays for its scanned appendix, not its whole body."""
    result = ocr_pdf_pages(_scanned_pdf([None, "RECEIPT"]), [2])
    assert result.attempted is True
    assert set(result.pages) == {2}


@needs_ocr
def test_recovered_text_carries_the_canonical_page_markers():
    """Provenance (#13894) must not depend on how a page happened to be read."""
    data = _result(_scanned_pdf(["ALPHA"]))
    assert "## Page 1" in data["extracted_text"]


@needs_ocr
def test_a_genuinely_blank_scan_reports_an_attempt_that_recovered_nothing():
    """Attempted-and-found-nothing differs from never-attempted."""
    data = _result(_scanned_pdf([None]))
    assert data["ocr_attempted"] is True
    assert data.get("ocr_pages") == []
    assert data["processing_status"] == "no_text_layer"
