# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Upload-path text-layer guards (#13884).

Before this fix, the upload endpoint's ``if not content.strip()`` guard only
caught a document whose flattened text was blank. A scan stamped with a page
number, Bates number, or filename on every page has non-empty text — pure
boilerplate — and reached the KB as an unsearchable document. These tests
call ``_extract_file_content`` and ``_has_usable_content`` — the exact
function the endpoint calls, not a reimplementation of its logic — directly
rather than the full HTTP endpoint (no test client / auth harness existed for
this route before this PR). Calling the real decision function is what makes
a mutation of it show up here instead of only in the endpoint at runtime.
"""

import io

import pytest


def _stamped_scan_pdf(pages: int = 5) -> bytes:
    pytest.importorskip("reportlab", reason="reportlab needed to synthesize a PDF fixture")
    pytest.importorskip("PIL", reason="Pillow needed to synthesize an image-only page")
    from PIL import Image
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    blank_page = ImageReader(Image.new("RGB", (600, 800), "white"))
    for i in range(1, pages + 1):
        pdf.drawImage(blank_page, 0, 0, width=400, height=500)
        pdf.setFont("Helvetica", 9)
        pdf.drawString(400, 20, f"Page {i} of {pages}")
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def _born_digital_pdf(text: str) -> bytes:
    pytest.importorskip("reportlab", reason="reportlab needed to synthesize a PDF fixture")
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.drawString(72, 720, text)
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def _upload_guard_usable(filename: str, file_content: bytes) -> bool:
    """Call the upload endpoint's real usability decision, not a copy of it."""
    from api.knowledge import _extract_file_content, _has_usable_content

    content, extracted_doc = _extract_file_content(filename, file_content)
    return _has_usable_content(content, extracted_doc)


def test_stamped_scan_fails_the_upload_guard_despite_nonzero_text():
    """#13884 finding 1: `content.strip()` alone would have let this through."""
    from api.knowledge import _extract_file_content

    content, extracted_doc = _extract_file_content("scan.pdf", _stamped_scan_pdf())

    assert content.strip() != "", "the stamp text itself is non-empty"
    assert extracted_doc is not None
    assert extracted_doc.has_usable_text_layer is False
    assert _upload_guard_usable("scan.pdf", _stamped_scan_pdf()) is False


def test_born_digital_pdf_passes_the_upload_guard_unchanged():
    """Regression guard: the common case must not pay for the scanned case."""
    raw = _born_digital_pdf("A full paragraph of real, born-digital prose content.")
    assert _upload_guard_usable("contract.pdf", raw) is True


def test_no_text_detail_names_ocr_for_a_stamped_scan():
    from api.knowledge import _extract_file_content, _no_text_detail

    _, extracted_doc = _extract_file_content("scan.pdf", _stamped_scan_pdf())
    detail = _no_text_detail(extracted_doc)

    assert "OCR" in detail
    assert "5 page" in detail


def test_no_text_detail_does_not_claim_ocr_for_a_blank_text_file():
    from api.knowledge import _no_text_detail

    assert "OCR" not in _no_text_detail(None)
