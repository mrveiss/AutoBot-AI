# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shared connector content-extraction helpers (#13884).

``extract_text_from_pdf`` throws away the per-page structure a caller needs
to tell a page-number-stamped scan (text present, nothing usable) from real
content. ``extract_pdf_document`` is the seam that keeps it — this pins that
it returns the same text ``extract_text_from_pdf`` always has, plus the
structure, and degrades to ``None``/``""`` the same way on a parse failure.
"""

import io

import pytest

from knowledge.connectors.content_extraction import extract_pdf_document, extract_text_from_pdf
from media.document.extraction import ExtractedDocument


def _pdf(text: str) -> bytes:
    pytest.importorskip("reportlab", reason="reportlab needed to synthesize a PDF fixture")
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.drawString(72, 720, text)
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def test_extract_pdf_document_returns_the_structured_result():
    raw = _pdf("A full paragraph of real prose content for this extraction test.")
    extracted = extract_pdf_document(raw)

    assert isinstance(extracted, ExtractedDocument)
    assert extracted.format == "pdf"
    assert extracted.has_usable_text_layer is True


def test_extract_text_from_pdf_still_returns_flattened_text():
    """Backward-compatible: existing callers of the string API are unaffected."""
    raw = _pdf("A full paragraph of real prose content for this extraction test.")
    assert "A full paragraph" in extract_text_from_pdf(raw)


def test_extract_pdf_document_returns_none_on_parse_failure():
    assert extract_pdf_document(b"not actually a pdf") is None


def test_extract_text_from_pdf_degrades_to_empty_string_on_parse_failure():
    assert extract_text_from_pdf(b"not actually a pdf") == ""
