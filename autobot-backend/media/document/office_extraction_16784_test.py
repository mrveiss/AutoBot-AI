# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The media pipeline never plain-texts a verified office document (#16784).

``extract_document`` dispatched pdf and docx and fell through to
``extract_plain_text`` for everything else, so a spreadsheet, presentation or
OpenDocument file was decoded as if its ZIP bytes were text. The result was
binary noise presented as document text, which then flowed into the knowledge
base and into prompts through retrieval.

The load-bearing property is **negative**: for these formats
``extract_document`` must never return ``format="text"``. A test that only
covers a healthy document would still pass if the fall-through came back, so
every case here checks a file that *cannot* be parsed and asserts it raises
rather than degrades.

Fixtures are built with ``zipfile`` rather than committed as binaries, so what
makes each one that format is visible in the test.
"""

from __future__ import annotations

import io
import zipfile

import pytest

from media.document.extraction import (
    DocumentDependencyError,
    DocumentExtractionError,
    extract_document,
    extract_office,
)


def _ooxml(part: str) -> bytes:
    """A ZIP carrying the one part that identifies an OOXML type, and nothing else."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(part, "<xml/>")
    return buffer.getvalue()


def _odf(mimetype: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("mimetype", mimetype)
        archive.writestr("content.xml", "<xml/>")
    return buffer.getvalue()


OFFICE_FIXTURES = {
    "xlsx": _ooxml("xl/workbook.xml"),
    "pptx": _ooxml("ppt/presentation.xml"),
    "odt": _odf("application/vnd.oasis.opendocument.text"),
    "ods": _odf("application/vnd.oasis.opendocument.spreadsheet"),
    "odp": _odf("application/vnd.oasis.opendocument.presentation"),
}


class TestZipBytesAreNeverReturnedAsText:
    """The defect itself: silent garbage is worse than a clear refusal."""

    @pytest.mark.parametrize("fmt", sorted(OFFICE_FIXTURES))
    def test_a_verified_office_file_raises_rather_than_degrading(self, fmt: str) -> None:
        with pytest.raises(DocumentExtractionError) as caught:
            extract_document(OFFICE_FIXTURES[fmt])
        assert fmt in str(caught.value), "the error does not name the format it could not read"

    @pytest.mark.parametrize("fmt", sorted(OFFICE_FIXTURES))
    def test_the_zip_bytes_never_reach_the_caller(self, fmt: str) -> None:
        """Belt and braces: whatever happens, it is not the archive decoded as text."""
        try:
            result = extract_document(OFFICE_FIXTURES[fmt])
        except DocumentExtractionError:
            return
        assert result.format != "text", f"{fmt} was plain-texted — the #16784 defect is back"
        assert "PK" not in result.text[:4]


class TestTheOtherFormatsAreUnchanged:
    """#16784 changes one branch; the others must dispatch exactly as before."""

    def test_genuine_plain_text_is_still_plain_text(self) -> None:
        extracted = extract_document(b"just text")
        assert extracted.format == "text"
        assert extracted.text == "just text"

    def test_a_docx_does_not_take_the_office_branch(self, monkeypatch) -> None:
        """docx has its own reader above; routing it here would be a regression."""
        import media.document.extraction as module

        def _fail(*args, **kwargs):
            raise AssertionError("docx must not reach extract_office")

        monkeypatch.setattr(module, "extract_office", _fail)
        with pytest.raises(DocumentExtractionError):
            extract_document(_ooxml("word/document.xml"))

    def test_a_plain_zip_is_not_treated_as_an_office_document(self) -> None:
        """No identifying member, so it is not a format we claim to read."""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("notes.txt", "hello")
        assert extract_document(buffer.getvalue()).format == "text"


class TestAMissingLibraryIsADeploymentGap:
    """The pipeline reports dependency and extraction errors differently.

    A missing parser library is a deployment gap, not a bad upload. The shared
    sync parser catches every exception per candidate and reports one
    "extraction failed" string, so the distinction has to be made before
    delegating or it is lost.
    """

    def test_an_absent_parser_module_raises_a_dependency_error(self, monkeypatch) -> None:
        import media.document.extraction as module

        monkeypatch.setattr(module.importlib.util, "find_spec", lambda name: None)
        with pytest.raises(DocumentDependencyError) as caught:
            extract_office(OFFICE_FIXTURES["xlsx"], "xlsx")
        assert "openpyxl" in str(caught.value)

    def test_a_dependency_error_is_still_an_extraction_error(self) -> None:
        """Callers catching the base class must keep catching both."""
        assert issubclass(DocumentDependencyError, DocumentExtractionError)


class TestARealDocumentRoundTrips:
    def test_a_real_xlsx_returns_its_cell_text(self, tmp_path) -> None:
        openpyxl = pytest.importorskip("openpyxl")
        workbook = openpyxl.Workbook()
        workbook.active["A1"] = "hello from a sheet"
        path = tmp_path / "book.xlsx"
        workbook.save(path)

        extracted = extract_document(path.read_bytes())
        assert extracted.format == "xlsx"
        assert "hello from a sheet" in extracted.text
