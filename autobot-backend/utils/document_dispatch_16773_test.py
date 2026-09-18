# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Document dispatch follows verified content, not the file's name (#16773).

``DocumentParser`` routed on a flat extension -> parser dict and ``DocumentExtractor`` on
``suffix.lower()``, so a renamed ``.xlsx`` reached the ODT parser or was refused. Both now
lead with the format the archive itself declares, and still try the name afterwards -- a
mismatch alone must never fail an extraction.
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from utils.document_extractors import DocumentExtractor
from utils.document_parser import DocumentParser


def _ooxml(path: Path, part: str) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr(part, "<xml/>")
    return path


@pytest.fixture
def unverifiable_file(tmp_path) -> Path:
    """A file that is neither a supported name nor a readable archive."""
    path = tmp_path / "mystery.bin"
    path.write_bytes(b"not a zip at all")
    return path


@pytest.fixture
def plain_text_file(tmp_path) -> Path:
    path = tmp_path / "notes.txt"
    path.write_text("plain words", encoding="utf-8")
    return path


def test_a_mislabeled_workbook_leads_with_its_verified_format(tmp_path):
    mislabeled = _ooxml(tmp_path / "budget.odt", "xl/workbook.xml")

    assert DocumentParser()._candidate_extensions(mislabeled) == [".xlsx", ".odt"]


def test_a_correctly_named_file_has_one_candidate(tmp_path):
    honest = _ooxml(tmp_path / "budget.xlsx", "xl/workbook.xml")

    assert DocumentParser()._candidate_extensions(honest) == [".xlsx"]


def test_an_unverifiable_unsupported_name_has_no_candidates(unverifiable_file):
    assert DocumentParser()._candidate_extensions(unverifiable_file) == []


@pytest.mark.asyncio
async def test_extract_text_refuses_only_when_nothing_is_supported(unverifiable_file):
    with pytest.raises(ValueError, match="Unsupported document format"):
        await DocumentParser().extract_text(unverifiable_file)


def test_the_name_is_still_tried_when_the_verified_parser_fails(tmp_path):
    """Both guesses are attempted: a wrong sniff must not cost a parseable document."""
    parser = DocumentParser()
    path = _ooxml(tmp_path / "report.odt", "xl/workbook.xml")

    def _dispatch(extension):
        if extension == ".xlsx":

            def _fail(_path, _metadata):
                raise ValueError("not really a workbook")

            return _fail

        return lambda _path, _metadata: "text from the odt parser"

    with patch.object(DocumentParser, "_get_parser_for_extension", side_effect=_dispatch):
        text, metadata = parser._extract_text_sync(path, [".xlsx", ".odt"])

    assert text == "text from the odt parser"
    assert metadata["format"] == ".odt"
    assert metadata["extraction_success"] is True


def test_a_document_no_candidate_can_parse_reports_the_failure(tmp_path):
    parser = DocumentParser()
    path = _ooxml(tmp_path / "report.odt", "xl/workbook.xml")

    def _fail(_path, _metadata):
        raise ValueError("unreadable")

    with patch.object(DocumentParser, "_get_parser_for_extension", return_value=_fail):
        text, metadata = parser._extract_text_sync(path, [".xlsx", ".odt"])

    assert text == ""
    assert metadata["extraction_success"] is False
    assert "unreadable" in metadata["extraction_error"]


@pytest.mark.asyncio
async def test_the_extractor_routes_a_word_document_named_as_text(tmp_path):
    """A .txt name would have been read as plain text, yielding ZIP bytes as "text"."""
    mislabeled = _ooxml(tmp_path / "notes.txt", "word/document.xml")

    with patch.object(DocumentExtractor, "extract_from_docx", new=AsyncMock(return_value="docx text")) as docx:
        result = await DocumentExtractor.extract_from_file(mislabeled)

    assert result == "docx text"
    docx.assert_awaited_once()


@pytest.mark.asyncio
async def test_the_extractor_routes_a_workbook_named_docx_to_the_office_path(tmp_path):
    mislabeled = _ooxml(tmp_path / "budget.docx", "xl/workbook.xml")

    with patch.object(DocumentExtractor, "extract_from_office", new=AsyncMock(return_value="sheet text")) as office:
        result = await DocumentExtractor.extract_from_file(mislabeled)

    assert result == "sheet text"
    office.assert_awaited_once()


@pytest.mark.asyncio
async def test_an_honest_text_file_is_untouched_by_the_sniff(plain_text_file):
    with patch.object(DocumentExtractor, "extract_from_text", new=AsyncMock(return_value="plain words")) as text:
        result = await DocumentExtractor.extract_from_file(plain_text_file)

    assert result == "plain words"
    text.assert_awaited_once()
