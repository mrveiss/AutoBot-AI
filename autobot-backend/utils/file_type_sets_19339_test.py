# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Behaviour of the canonical file-type sets (#19339)."""

import pytest

from utils.document_extractors import DocumentExtractor
from utils.file_categorization import HTML_EXTENSIONS
from utils.file_types import DOCX_EXTENSIONS, TEXT_FILE_EXTENSIONS


def test_legacy_doc_is_not_a_docx() -> None:
    assert DOCX_EXTENSIONS == frozenset({".docx"})
    assert ".doc" not in DocumentExtractor.SUPPORTED_FORMATS["docx"]


@pytest.fixture
def legacy_doc(tmp_path):
    path = tmp_path / "old.doc"
    path.write_bytes(b"\xd0\xcf\x11\xe0 not a zip")
    return path


@pytest.mark.asyncio
async def test_a_doc_goes_to_the_parsers_textract_fallback(legacy_doc, monkeypatch) -> None:
    """Legacy .doc is routed to DocumentParser, which reads it when textract is installed."""
    from utils.document_parser import document_parser

    async def parsed(path):
        return "old word text", {"extraction_success": True}

    monkeypatch.setattr(document_parser, "extract_text", parsed)
    assert await DocumentExtractor.extract_from_file(legacy_doc) == "old word text"


@pytest.mark.asyncio
async def test_a_doc_without_textract_is_an_error_never_an_empty_ingest(legacy_doc, monkeypatch) -> None:
    from utils.document_parser import document_parser

    async def no_textract(path):
        return "", {"extraction_success": True, "warning": "textract required for .doc files"}

    monkeypatch.setattr(document_parser, "extract_text", no_textract)
    with pytest.raises(ValueError, match="textract required"):
        await DocumentExtractor.extract_from_file(legacy_doc)


def test_the_extractor_html_formats_are_the_canonical_set() -> None:
    assert set(DocumentExtractor.SUPPORTED_FORMATS["html"]) == HTML_EXTENSIONS


def test_the_text_set_covers_every_extension_the_three_old_copies_accepted() -> None:
    assert {".csv", ".json", ".htm", ".rst", ".xml", ".kt", ".tsx", ".md", ".yaml"} <= TEXT_FILE_EXTENSIONS


def test_a_textract_failure_is_recorded_so_the_extractor_rejects_it(legacy_doc, monkeypatch) -> None:
    """textract raising (not just missing) used to return "" with no warning: an empty ingest (#19696 review)."""
    import sys
    import types

    from utils.document_parser import document_parser

    broken = types.SimpleNamespace(process=lambda path: (_ for _ in ()).throw(RuntimeError("corrupt OLE stream")))
    monkeypatch.setitem(sys.modules, "textract", broken)
    metadata: dict = {}
    assert document_parser._parse_doc_fallback(legacy_doc, metadata) == ""
    assert metadata["warning"] == ".doc parse failed: corrupt OLE stream"
