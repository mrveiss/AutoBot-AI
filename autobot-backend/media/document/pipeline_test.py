# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# Document Pipeline Tests
# Issue #932: Implement actual document processing

"""Unit tests for DocumentPipeline."""

import base64
import io
from unittest.mock import patch

import pytest

from media.core.types import MediaInput, MediaType, ProcessingIntent
from media.document.extraction import (
    DocumentDependencyError,
    DocumentExtractionError,
    ExtractedDocument,
    detect_format,
)
from media.document.pipeline import DocumentPipeline


def _make_pdf(pages: list[str]) -> bytes:
    """Build a real PDF with a text layer, so extraction is exercised end to end."""
    reportlab = pytest.importorskip("reportlab", reason="reportlab needed to synthesize a PDF fixture")
    from reportlab.pdfgen import canvas  # noqa: F401  (import validated by importorskip)

    buffer = io.BytesIO()
    pdf = reportlab.pdfgen.canvas.Canvas(buffer)
    for text in pages:
        pdf.drawString(72, 720, text)
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def _make_input(data, mime_type="text/plain", intent=None):
    return MediaInput(
        media_id="test-doc",
        media_type=MediaType.DOCUMENT,
        intent=intent or ProcessingIntent.ANALYSIS,
        data=data,
        mime_type=mime_type,
        metadata={},
    )


class TestDocumentPipelineDecoding:
    """Tests for _decode_input helper."""

    def test_bytes_passthrough(self):
        pipe = DocumentPipeline()
        raw = b"hello bytes"
        assert pipe._decode_input(raw) == raw

    def test_base64_string(self):
        pipe = DocumentPipeline()
        raw = b"hello b64"
        encoded = base64.b64encode(raw).decode()
        assert pipe._decode_input(encoded) == raw

    def test_invalid_type_raises(self):
        pipe = DocumentPipeline()
        with pytest.raises(ValueError, match="Unsupported"):
            pipe._decode_input(12345)


class TestDocumentPipelineFormatDetection:
    """Format detection moved to the canonical core (#13893); assert via the pipeline result."""

    @pytest.mark.asyncio
    async def test_pdf_magic_bytes_beat_a_wrong_mime_type(self):
        pipe = DocumentPipeline()
        result = await pipe._process_impl(_make_input(_make_pdf(["body"]), "text/plain"))
        assert result.result_data["format"] == "pdf"

    @pytest.mark.asyncio
    async def test_text_fallback(self):
        pipe = DocumentPipeline()
        result = await pipe._process_impl(_make_input(b"just text", "text/plain"))
        assert result.result_data["format"] == "text"

    def test_detection_helpers_live_in_the_canonical_core(self):
        """The pipeline must not grow its own detector back."""
        assert detect_format(b"%PDF-1.4 content", "") == "pdf"
        assert detect_format(b"PK" + b"\x00" * 100 + b"word/document.xml", "") == "docx"
        assert detect_format(b"plaintext", "application/pdf") == "pdf"
        assert (
            detect_format(
                b"not real docx bytes",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
            == "docx"
        )


class TestDocumentPipelineTextExtraction:
    """Plain-text extraction, asserted through the public pipeline entry point."""

    @pytest.mark.asyncio
    async def test_utf8_text(self):
        pipe = DocumentPipeline()
        result = await pipe._process_impl(_make_input(b"Hello UTF-8 world", "text/plain"))
        data = result.result_data
        assert data["format"] == "text"
        assert data["extracted_text"] == "Hello UTF-8 world"
        assert data["confidence"] == 1.0

    @pytest.mark.asyncio
    async def test_latin1_fallback(self):
        pipe = DocumentPipeline()
        result = await pipe._process_impl(_make_input(b"caf\xe9", "text/plain"))
        assert "caf" in result.result_data["extracted_text"]
        assert result.result_data["confidence"] == 1.0

    @pytest.mark.asyncio
    async def test_line_and_char_count(self):
        pipe = DocumentPipeline()
        content = b"line1\nline2\nline3"
        result = await pipe._process_impl(_make_input(content, "text/plain"))
        assert result.result_data["line_count"] == 3
        assert result.result_data["char_count"] == len(content.decode())


class TestDocumentPipelinePdf:
    """PDF extraction against real PDFs rather than a mocked reader."""

    @pytest.mark.asyncio
    async def test_pdf_extraction_success(self):
        pipe = DocumentPipeline()
        result = await pipe._process_impl(_make_input(_make_pdf(["page content"]), "application/pdf"))
        data = result.result_data

        assert data["format"] == "pdf"
        assert "page content" in data["extracted_text"]
        assert data["page_count"] == 1
        assert data["confidence"] == 0.95

    @pytest.mark.asyncio
    async def test_pdf_extraction_error_is_reported_as_error(self):
        pipe = DocumentPipeline()
        with patch(
            "media.document.pipeline.extract_document",
            side_effect=DocumentExtractionError("bad pdf"),
        ):
            result = await pipe._process_impl(_make_input(b"%PDF-1.4 garbage", "application/pdf"))

        assert result.result_data["processing_status"] == "error"
        assert "bad pdf" in result.result_data["error"]

    @pytest.mark.asyncio
    async def test_missing_library_is_unavailable_not_error(self):
        """A deployment gap must stay distinguishable from a corrupt upload (#13893)."""
        pipe = DocumentPipeline()
        with patch(
            "media.document.pipeline.extract_document",
            side_effect=DocumentDependencyError("PDF support requires the pypdf library"),
        ):
            result = await pipe._process_impl(_make_input(b"%PDF-1.4", "application/pdf"))

        data = result.result_data
        assert data["processing_status"] == "unavailable"
        assert data["confidence"] == 0.0
        assert "pypdf" in data["unavailability_reason"]


class TestDocumentPipelineDocx:
    """DOCX extraction, asserted through the pipeline seam."""

    @pytest.mark.asyncio
    async def test_docx_unavailable_result(self):
        pipe = DocumentPipeline()
        with patch(
            "media.document.pipeline.extract_document",
            side_effect=DocumentDependencyError("DOCX support requires the python-docx library"),
        ):
            result = await pipe._process_impl(_make_input(b"PK data", "application/vnd.openxmlformats"))
        assert result.result_data["processing_status"] == "unavailable"

    @pytest.mark.asyncio
    async def test_docx_extraction_success(self):
        pipe = DocumentPipeline()
        extracted = ExtractedDocument(
            format="docx",
            text="Paragraph text",
            tables=(),
            info={"title": "Doc Title", "author": "Author", "subject": "", "keywords": ""},
        )
        with patch("media.document.pipeline.extract_document", return_value=extracted):
            result = await pipe._process_impl(_make_input(b"PK data", "application/vnd.openxmlformats"))

        data = result.result_data
        assert data["format"] == "docx"
        assert data["extracted_text"] == "Paragraph text"
        assert data["paragraph_count"] == 1
        assert data["document_info"]["title"] == "Doc Title"
        assert data["confidence"] == 0.95


class TestDocumentPipelineAsync:
    """Tests for async processing end-to-end."""

    @pytest.mark.asyncio
    async def test_process_text_async(self):
        pipe = DocumentPipeline()
        media_input = _make_input(b"plain text content", "text/plain")
        result = await pipe._process_impl(media_input)
        assert result.success is True
        assert result.result_data["format"] == "text"
        assert "plain text content" in result.result_data["extracted_text"]
