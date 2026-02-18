# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Document Pipeline Tests
# Issue #932: Implement actual document processing

"""Unit tests for DocumentPipeline."""

import base64
from unittest.mock import MagicMock, patch

import pytest
from media.core.types import MediaInput, MediaType, ProcessingIntent
from media.document.pipeline import DocumentPipeline


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
    """Tests for _detect_format."""

    def test_pdf_magic_bytes(self):
        pipe = DocumentPipeline()
        assert pipe._detect_format(b"%PDF-1.4 content", "") == "pdf"

    def test_docx_magic_bytes(self):
        pipe = DocumentPipeline()
        raw = b"PK" + b"\x00" * 100 + b"word/document.xml"
        assert pipe._detect_format(raw, "") == "docx"

    def test_pdf_via_mime(self):
        pipe = DocumentPipeline()
        assert pipe._detect_format(b"plaintext", "application/pdf") == "pdf"

    def test_docx_via_mime(self):
        pipe = DocumentPipeline()
        raw = b"not real docx bytes"
        assert (
            pipe._detect_format(
                raw,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
            == "docx"
        )

    def test_text_fallback(self):
        pipe = DocumentPipeline()
        assert pipe._detect_format(b"just text", "text/plain") == "text"


class TestDocumentPipelineTextExtraction:
    """Tests for plain text extraction."""

    def test_utf8_text(self):
        pipe = DocumentPipeline()
        content = b"Hello UTF-8 world"
        result = pipe._extract_text(content, "text/plain", {})
        assert result["format"] == "text"
        assert result["extracted_text"] == "Hello UTF-8 world"
        assert result["confidence"] == 1.0

    def test_latin1_fallback(self):
        pipe = DocumentPipeline()
        content = b"caf\xe9"  # café in latin-1
        result = pipe._extract_text(content, "text/plain", {})
        assert "caf" in result["extracted_text"]
        assert result["confidence"] == 1.0

    def test_line_and_char_count(self):
        pipe = DocumentPipeline()
        content = b"line1\nline2\nline3"
        result = pipe._extract_text(content, "text/plain", {})
        assert result["line_count"] == 3
        assert result["char_count"] == len("line1\nline2\nline3")


class TestDocumentPipelinePdf:
    """Tests for PDF extraction."""

    def test_pdf_unavailable_result(self):
        pipe = DocumentPipeline()
        with patch("media.document.pipeline._PYPDF_AVAILABLE", False):
            result = pipe._extract_pdf(b"%PDF-1.4", {})
        assert result["processing_status"] == "unavailable"
        assert result["confidence"] == 0.0

    def test_pdf_extraction_success(self):
        pipe = DocumentPipeline()
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "page content"
        mock_reader = MagicMock()
        mock_reader.pages = [mock_page]
        mock_reader.metadata = {"/Title": "Test Doc", "/Author": "Author"}

        with patch("media.document.pipeline._PYPDF_AVAILABLE", True), patch(
            "media.document.pipeline.PdfReader", return_value=mock_reader
        ):
            result = pipe._extract_pdf(b"%PDF-1.4", {"source": "test"})

        assert result["format"] == "pdf"
        assert result["extracted_text"] == "page content"
        assert result["page_count"] == 1
        assert result["document_info"]["title"] == "Test Doc"
        assert result["confidence"] == 0.95

    def test_pdf_extraction_error(self):
        pipe = DocumentPipeline()
        with patch("media.document.pipeline._PYPDF_AVAILABLE", True), patch(
            "media.document.pipeline.PdfReader", side_effect=Exception("bad pdf")
        ):
            result = pipe._extract_pdf(b"garbage", {})
        assert result["processing_status"] == "error"
        assert "bad pdf" in result["error"]


class TestDocumentPipelineDocx:
    """Tests for DOCX extraction."""

    def test_docx_unavailable_result(self):
        pipe = DocumentPipeline()
        with patch("media.document.pipeline._DOCX_AVAILABLE", False):
            result = pipe._extract_docx(b"PK data", {})
        assert result["processing_status"] == "unavailable"

    def test_docx_extraction_success(self):
        pipe = DocumentPipeline()
        mock_para = MagicMock()
        mock_para.text = "Paragraph text"
        mock_doc = MagicMock()
        mock_doc.paragraphs = [mock_para]
        mock_doc.tables = []
        mock_doc.core_properties.title = "Doc Title"
        mock_doc.core_properties.author = "Author"
        mock_doc.core_properties.subject = ""
        mock_doc.core_properties.keywords = ""

        with patch("media.document.pipeline._DOCX_AVAILABLE", True), patch(
            "media.document.pipeline.DocxDocument", return_value=mock_doc
        ):
            result = pipe._extract_docx(b"PK data", {})

        assert result["format"] == "docx"
        assert result["extracted_text"] == "Paragraph text"
        assert result["paragraph_count"] == 1
        assert result["document_info"]["title"] == "Doc Title"
        assert result["confidence"] == 0.95


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
